"""Local child-process run controller for CLI and TUI operators."""

from __future__ import annotations

import csv
import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator

from .config import RunConfig
from .events import (
    RunAgentTraceEvent,
    RunArtifactEvent,
    RunEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunLogEvent,
    RunOrderEvent,
    RunPositionEvent,
    RunProgressEvent,
    RunStartedEvent,
)

_SENTINEL = object()


class RunHandle:
    """Handle for one local LumiBot child process."""

    def __init__(self, config: RunConfig, process: subprocess.Popen[str]) -> None:
        self.config = config
        self.process = process
        self.run_id = config.run_id
        self._events: queue.Queue[RunEvent | object] = queue.Queue()
        self._started_at = time.monotonic()
        self._stop_requested = threading.Event()
        self._finished = threading.Event()
        self._seen_artifacts: set[str] = set()
        self._threads: list[threading.Thread] = []

        self._emit(
            RunStartedEvent(
                run_id=self.run_id,
                command=config.command(),
                cwd=str(config.resolved_cwd),
                pid=process.pid,
                config=config.display_config(),
            )
        )
        self._start_threads()

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

    def events(self) -> Iterator[RunEvent]:
        """Yield events until the child process exits."""
        while True:
            item = self._events.get()
            if item is _SENTINEL:
                break
            yield item

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the child process to stop, escalating from SIGINT to terminate."""
        if self.process.poll() is not None:
            return
        self._stop_requested.set()
        try:
            if os.name == "posix":
                os.killpg(self.process.pid, signal.SIGINT)
            else:
                self.process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return
        except Exception:
            self.process.terminate()
            return

        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.terminate()

    def _start_threads(self) -> None:
        for stream_name, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._read_stream,
                args=(stream_name, stream),
                name=f"lumibot-run-{self.run_id}-{stream_name}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

        for target, name in (
            (self._watch_progress_csv, "progress"),
            (self._monitor_process, "monitor"),
        ):
            thread = threading.Thread(
                target=target,
                name=f"lumibot-run-{self.run_id}-{name}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _emit(self, event: RunEvent) -> None:
        self._events.put(event)

    def _read_stream(self, stream_name: str, stream) -> None:
        for line in stream:
            text = line.rstrip("\n")
            if not text:
                continue
            self._emit(RunLogEvent(run_id=self.run_id, stream=stream_name, line=text, level=_infer_log_level(text)))

    def _watch_progress_csv(self) -> None:
        path = self.config.progress_csv_path
        last_mtime = None
        while not self._finished.is_set():
            if path.exists():
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    time.sleep(0.5)
                    continue
                if mtime != last_mtime:
                    last_mtime = mtime
                    self._emit_progress_from_csv(path)
            time.sleep(0.5)

    def _emit_progress_from_csv(self, path: Path) -> None:
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except Exception as exc:
            self._emit(RunLogEvent(run_id=self.run_id, stream="runtime", line=f"Could not read progress CSV: {exc}"))
            return
        if not rows:
            return

        row = rows[-1]
        download_status = _parse_json_object(row.get("download_status"))
        self._emit(
            RunProgressEvent(
                run_id=self.run_id,
                percent=_parse_float(row.get("percent")),
                elapsed=row.get("elapsed") or "",
                eta=row.get("eta") or "",
                portfolio_value=row.get("portfolio_value") or "",
                simulation_date=row.get("simulation_date") or "",
                cash=row.get("cash") or "",
                total_return_pct=row.get("total_return_pct") or "",
                download_status=download_status,
            )
        )

        for position in _parse_json_list(row.get("positions_json")):
            self._emit(RunPositionEvent(run_id=self.run_id, position=position))
        for order in _parse_json_list(row.get("orders_json")):
            self._emit(RunOrderEvent(run_id=self.run_id, order=order))

    def _monitor_process(self) -> None:
        returncode = self.process.wait()
        duration = round(time.monotonic() - self._started_at, 3)
        self._finished.set()
        if self.config.progress_csv_path.exists():
            self._emit_progress_from_csv(self.config.progress_csv_path)
        self._emit_discovered_artifacts()
        if returncode == 0:
            self._emit(RunFinishedEvent(run_id=self.run_id, returncode=returncode, duration_seconds=duration))
        else:
            message = "Run stopped" if self._stop_requested.is_set() else f"Run failed with exit code {returncode}"
            self._emit(RunFailedEvent(run_id=self.run_id, returncode=returncode, message=message, duration_seconds=duration))
        self._events.put(_SENTINEL)

    def _emit_discovered_artifacts(self) -> None:
        log_dir = self.config.resolved_log_dir
        if not log_dir.exists():
            return
        for path in sorted(item for item in log_dir.rglob("*") if item.is_file()):
            key = str(path.resolve())
            if key in self._seen_artifacts:
                continue
            self._seen_artifacts.add(key)
            artifact_type = _artifact_type(path)
            self._emit(RunArtifactEvent.from_path(self.run_id, path, artifact_type=artifact_type))
            if artifact_type == "agent_trace":
                self._emit(RunAgentTraceEvent(run_id=self.run_id, path=str(path), name=path.name, summary="Agent trace artifact"))


class RunController:
    """Launch local LumiBot script runs and expose typed event streams."""

    def start(self, config: RunConfig) -> RunHandle:
        config.resolved_log_dir.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            config.command(),
            cwd=str(config.resolved_cwd),
            env=config.build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=os.name == "posix",
        )
        return RunHandle(config=config, process=process)


def _infer_log_level(line: str) -> str | None:
    for level in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        if f"| {level} |" in line or line.startswith(level):
            return level
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_list(value: str | None) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _artifact_type(path: Path) -> str:
    name = path.name.lower()
    if "agent" in name and ("trace" in name or "detail" in name or "memory" in name):
        return "agent_trace"
    if "tearsheet" in name:
        return "tearsheet"
    if "trade" in name:
        return "trades"
    if "stats" in name:
        return "stats"
    if "progress" in name:
        return "progress"
    if "settings" in name:
        return "settings"
    return "file"
