"""Run queue and subprocess orchestration for the Local Backtest Studio."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import (
    chart_data,
    extract_metrics,
    list_artifacts,
    read_json,
    read_progress,
    redact_text,
    write_json,
)
from .models import (
    StudioValidationError,
    build_initial_status,
    build_preflight,
    materialize_template_strategy,
    new_run_id,
    normalize_run_spec,
)


class RunManager:
    """Single-worker subprocess queue for Studio backtests."""

    def __init__(self, workspace: Path, runs_dir: Path):
        self.workspace = workspace.resolve()
        self.runs_dir = runs_dir.resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._canceled: set[str] = set()
        self._worker = threading.Thread(target=self._worker_loop, name="lumibot-studio-runner", daemon=True)
        self._worker.start()

    def submit(self, payload: dict) -> dict:
        run_id = new_run_id()
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)

        spec = normalize_run_spec(payload, self.workspace, run_dir, run_id=run_id)
        materialize_template_strategy(spec)
        preflight = build_preflight(spec, self.runs_dir)
        failures = [check for check in preflight if check["status"] == "fail"]
        if failures:
            raise StudioValidationError("; ".join(check["detail"] for check in failures))

        write_json(run_dir / "run.json", spec)
        status = build_initial_status(run_id)
        status["preflight"] = preflight
        status["artifacts"] = list_artifacts(run_dir)
        write_json(run_dir / "status.json", status)
        self._queue.put(run_id)
        return self.get_run(run_id)

    def preflight(self, payload: dict) -> dict:
        run_id = str(payload.get("run_id") or "preflight")
        with tempfile.TemporaryDirectory(prefix=".preflight_", dir=self.runs_dir) as tmp_dir:
            run_dir = Path(tmp_dir)
            spec = normalize_run_spec(payload, self.workspace, run_dir, run_id=run_id)
            if spec["strategy"]["source"] == "template":
                materialize_template_strategy(spec)
            return {"spec": spec, "checks": build_preflight(spec, self.runs_dir)}

    def list_runs(self) -> list[dict]:
        runs = []
        for path in sorted(self.runs_dir.iterdir(), reverse=True):
            if not path.is_dir():
                continue
            status = read_json(path / "status.json", {})
            if status:
                runs.append(self._augment_status(path.name, status))
        return runs

    def get_run(self, run_id: str) -> dict:
        run_dir = self.run_dir(run_id)
        status = read_json(run_dir / "status.json", None)
        if not status:
            raise FileNotFoundError(run_id)
        status = self._augment_status(run_id, status)
        spec = read_json(run_dir / "run.json", {})
        return {"run_id": run_id, "spec": spec, "status": status}

    def get_logs(self, run_id: str, offset: int = 0) -> dict:
        path = self.run_dir(run_id) / "output.log"
        if not path.exists():
            return {"offset": 0, "next_offset": 0, "text": ""}
        text = path.read_text(encoding="utf-8", errors="replace")
        offset = max(0, int(offset or 0))
        return {
            "offset": offset,
            "next_offset": len(text),
            "text": redact_text(text[offset:]),
        }

    def cancel(self, run_id: str) -> dict:
        with self._lock:
            self._canceled.add(run_id)
            process = self._processes.get(run_id)
            if process and process.poll() is None:
                process.terminate()
            run_dir = self.run_dir(run_id)
            status = read_json(run_dir / "status.json", build_initial_status(run_id))
            if status.get("state") == "queued":
                status.update(
                    {
                        "state": "canceled",
                        "phase": "canceled",
                        "ended_at": datetime.now().isoformat(),
                        "error_summary": "Run canceled before it started.",
                    }
                )
                write_json(run_dir / "status.json", status)
        return self.get_run(run_id)

    def run_dir(self, run_id: str) -> Path:
        safe_run_id = str(run_id).replace("/", "_").replace("\\", "_")
        return self.runs_dir / safe_run_id

    def chart_data(self, run_id: str) -> dict:
        return chart_data(self.run_dir(run_id))

    def _worker_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                if run_id in self._canceled:
                    continue
                self._execute_run(run_id)
            finally:
                self._queue.task_done()

    def _execute_run(self, run_id: str) -> None:
        run_dir = self.run_dir(run_id)
        status = read_json(run_dir / "status.json", build_initial_status(run_id))
        status.update(
            {
                "state": "running",
                "phase": "starting",
                "started_at": datetime.now().isoformat(),
                "progress_pct": 0.0,
            }
        )
        write_json(run_dir / "status.json", status)
        log_path = run_dir / "output.log"
        env = os.environ.copy()
        package_root = Path(__file__).resolve().parents[2]
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(package_root)
            if not existing_pythonpath
            else os.pathsep.join([str(package_root), existing_pythonpath])
        )
        cmd = [sys.executable, "-m", "lumibot.studio.runner", str(run_dir / "run.json")]

        start = time.monotonic()
        process = subprocess.Popen(
            cmd,
            cwd=str(run_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with self._lock:
            self._processes[run_id] = process

        try:
            with log_path.open("a", encoding="utf-8") as handle:
                while True:
                    line = process.stdout.readline() if process.stdout is not None else ""
                    if line:
                        handle.write(redact_text(line))
                        handle.flush()
                    self._refresh_running_status(run_id, phase="running")
                    if process.poll() is not None:
                        remaining = process.stdout.read() if process.stdout is not None else ""
                        if remaining:
                            handle.write(redact_text(remaining))
                        break
                    if run_id in self._canceled:
                        process.terminate()
                    time.sleep(0.2)
        finally:
            with self._lock:
                self._processes.pop(run_id, None)

        return_code = process.wait()
        runtime_seconds = time.monotonic() - start
        final_status = read_json(run_dir / "status.json", build_initial_status(run_id))
        final_status["exit_code"] = return_code
        final_status["ended_at"] = datetime.now().isoformat()
        final_status["artifacts"] = list_artifacts(run_dir)
        final_status["metrics_summary"] = extract_metrics(run_dir, runtime_seconds=runtime_seconds)
        if run_id in self._canceled or return_code == 130:
            final_status["state"] = "canceled"
            final_status["phase"] = "canceled"
            final_status["error_summary"] = "Run canceled."
        elif return_code == 0:
            final_status["state"] = "completed"
            final_status["phase"] = "completed"
            final_status["progress_pct"] = 100.0
            final_status["error_summary"] = _no_trade_warning(final_status)
        else:
            final_status["state"] = "failed"
            final_status["phase"] = "failed"
            final_status["error_summary"] = self._last_error_summary(log_path)
        write_json(run_dir / "status.json", final_status)

    def _refresh_running_status(self, run_id: str, phase: str) -> None:
        run_dir = self.run_dir(run_id)
        status = read_json(run_dir / "status.json", build_initial_status(run_id))
        progress = read_progress(run_dir)
        if progress.get("progress_pct") is not None:
            status["progress_pct"] = progress["progress_pct"]
        if progress.get("current_datetime"):
            status["current_datetime"] = progress["current_datetime"]
        status["phase"] = phase
        status["artifacts"] = list_artifacts(run_dir)
        write_json(run_dir / "status.json", status)

    def _augment_status(self, run_id: str, status: dict) -> dict:
        run_dir = self.run_dir(run_id)
        progress = read_progress(run_dir)
        if status.get("state") == "running":
            if progress.get("progress_pct") is not None:
                status["progress_pct"] = progress["progress_pct"]
            if progress.get("current_datetime"):
                status["current_datetime"] = progress["current_datetime"]
        status["artifacts"] = list_artifacts(run_dir)
        return status

    def _last_error_summary(self, log_path: Path) -> str:
        if not log_path.exists():
            return "Backtest failed without captured logs."
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            stripped = line.strip()
            if stripped and ("Error" in stripped or "Exception" in stripped or "Traceback" in stripped):
                return redact_text(stripped[-500:])
        return redact_text("\n".join(lines[-5:])[-500:] or "Backtest failed.")


def _no_trade_warning(status: dict) -> str | None:
    metrics = status.get("metrics_summary") or {}
    number_of_trades = metrics.get("number_of_trades")
    if number_of_trades == 0:
        return "Run completed, but no trades were recorded."
    return None
