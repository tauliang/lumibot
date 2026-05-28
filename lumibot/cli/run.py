"""Implementation of ``lumibot run``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from lumibot.studio.artifacts import extract_metrics, list_artifacts, read_json, read_progress, redact_text, write_json
from lumibot.studio.models import (
    StudioValidationError,
    build_initial_status,
    build_preflight,
    materialize_template_strategy,
    new_run_id,
    normalize_run_spec,
)

from .config import build_run_payload, read_lumibot_config, resolve_config_path, resolve_runs_dir, resolve_workspace


def run_command(args) -> int:
    config_path = resolve_config_path(args.config)
    config = read_lumibot_config(config_path)
    workspace = resolve_workspace(args, config_path)
    runs_dir = resolve_runs_dir(args, workspace, config)
    run_id = new_run_id()
    run_dir = runs_dir / run_id

    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        payload = build_run_payload(args, workspace, config)
        spec = normalize_run_spec(payload, workspace, run_dir, run_id=run_id)
        materialize_template_strategy(spec)
        preflight = build_preflight(spec, runs_dir)
        write_json(run_dir / "run.json", spec)

        status = build_initial_status(run_id)
        status["preflight"] = preflight
        status["artifacts"] = list_artifacts(run_dir)
        write_json(run_dir / "status.json", status)
    except (OSError, StudioValidationError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "run_id": run_id, "run_dir": str(run_dir), "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}")
        return 2

    failures = [check for check in preflight if check["status"] == "fail"]
    if failures:
        status.update(
            {
                "state": "failed",
                "phase": "preflight",
                "ended_at": datetime.now().isoformat(),
                "exit_code": 2,
                "error_summary": "; ".join(check["detail"] for check in failures),
            }
        )
        write_json(run_dir / "status.json", status)
        if args.json:
            print(json.dumps(_result_payload(run_dir, spec, status), indent=2, sort_keys=True))
        else:
            _print_preflight(preflight)
            print(f"Run was not started. See {run_dir}")
        return 2

    try:
        status = _execute_run(run_id, run_dir, stream=not args.json)
    except KeyboardInterrupt:
        status = read_json(run_dir / "status.json", build_initial_status(run_id))
        if not args.json:
            print("\nRun canceled.")
        else:
            print(json.dumps(_result_payload(run_dir, spec, status), indent=2, sort_keys=True, default=str))
        return 130
    if args.json:
        print(json.dumps(_result_payload(run_dir, spec, status), indent=2, sort_keys=True, default=str))
    else:
        _print_summary(run_dir, status)
    return 0 if status.get("state") == "completed" else int(status.get("exit_code") or 1)


def _execute_run(run_id: str, run_dir: Path, stream: bool) -> dict:
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

    env = os.environ.copy()
    package_root = Path(__file__).resolve().parents[2]
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(package_root) if not existing_pythonpath else os.pathsep.join([str(package_root), existing_pythonpath])
    cmd = [sys.executable, "-m", "lumibot.studio.runner", str(run_dir / "run.json")]
    log_path = run_dir / "output.log"
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
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            while True:
                line = process.stdout.readline() if process.stdout is not None else ""
                if line:
                    redacted = redact_text(line)
                    handle.write(redacted)
                    handle.flush()
                    if stream:
                        print(redacted, end="")
                _refresh_running_status(run_id, run_dir)
                if process.poll() is not None:
                    remaining = process.stdout.read() if process.stdout is not None else ""
                    if remaining:
                        redacted = redact_text(remaining)
                        handle.write(redacted)
                        if stream:
                            print(redacted, end="")
                    break
                time.sleep(0.2)
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        _finish_status(run_id, run_dir, process.returncode or 130, time.monotonic() - start, canceled=True)
        raise

    return _finish_status(run_id, run_dir, process.wait(), time.monotonic() - start)


def _refresh_running_status(run_id: str, run_dir: Path) -> None:
    status = read_json(run_dir / "status.json", build_initial_status(run_id))
    progress = read_progress(run_dir)
    if progress.get("progress_pct") is not None:
        status["progress_pct"] = progress["progress_pct"]
    if progress.get("current_datetime"):
        status["current_datetime"] = progress["current_datetime"]
    status["phase"] = "running"
    status["artifacts"] = list_artifacts(run_dir)
    write_json(run_dir / "status.json", status)


def _finish_status(run_id: str, run_dir: Path, exit_code: int, runtime_seconds: float, canceled: bool = False) -> dict:
    status = read_json(run_dir / "status.json", build_initial_status(run_id))
    status["exit_code"] = exit_code
    status["ended_at"] = datetime.now().isoformat()
    status["artifacts"] = list_artifacts(run_dir)
    status["metrics_summary"] = extract_metrics(run_dir, runtime_seconds=runtime_seconds)
    if canceled or exit_code == 130:
        status["state"] = "canceled"
        status["phase"] = "canceled"
        status["error_summary"] = "Run canceled."
    elif exit_code == 0:
        status["state"] = "completed"
        status["phase"] = "completed"
        status["progress_pct"] = 100.0
        status["error_summary"] = _no_trade_warning(status)
    else:
        status["state"] = "failed"
        status["phase"] = "failed"
        status["error_summary"] = _last_error_summary(run_dir / "output.log")
    write_json(run_dir / "status.json", status)
    return status


def _last_error_summary(log_path: Path) -> str:
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
    if metrics.get("number_of_trades") == 0:
        return "Run completed, but no trades were recorded."
    return None


def _result_payload(run_dir: Path, spec: dict, status: dict) -> dict:
    return {
        "ok": status.get("state") == "completed",
        "run_id": status.get("run_id"),
        "run_dir": str(run_dir),
        "spec": spec,
        "status": status,
    }


def _print_preflight(checks: list[dict]) -> None:
    for check in checks:
        print(f"{check['status'].upper():4} {check['title']}: {check['detail']}")


def _print_summary(run_dir: Path, status: dict[str, Any]) -> None:
    print("")
    print(f"Run {status.get('state')}: {status.get('run_id')}")
    print(f"Run directory: {run_dir}")
    metrics = status.get("metrics_summary") or {}
    if metrics:
        _print_metric("Final portfolio value", metrics.get("final_portfolio_value"))
        _print_metric("Total return", metrics.get("total_return"), percent=True)
        _print_metric("Sharpe", metrics.get("sharpe"))
        _print_metric("Max drawdown", metrics.get("max_drawdown"), percent=True)
        _print_metric("Trades", metrics.get("number_of_trades"))
    if status.get("error_summary"):
        print(f"Note: {status['error_summary']}")
    artifacts = [artifact["name"] for artifact in status.get("artifacts") or []]
    if artifacts:
        print("Artifacts: " + ", ".join(artifacts))


def _print_metric(label: str, value: Any, percent: bool = False) -> None:
    if value is None:
        return
    if percent and isinstance(value, (int, float)):
        print(f"{label}: {value:.2%}")
    else:
        print(f"{label}: {value}")
