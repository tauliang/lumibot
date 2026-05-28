"""Implementation of ``lumibot doctor``."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from lumibot.studio.models import StudioValidationError, build_preflight, materialize_template_strategy, normalize_run_spec

from .config import build_run_payload, read_lumibot_config, resolve_config_path, resolve_runs_dir, resolve_workspace


def doctor_command(args) -> int:
    config_path = resolve_config_path(args.config)
    config = read_lumibot_config(config_path)
    workspace = resolve_workspace(args, config_path)
    runs_dir = resolve_runs_dir(args, workspace, config)

    if args.fix:
        runs_dir.mkdir(parents=True, exist_ok=True)

    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        payload = build_run_payload(args, workspace, config)
        with tempfile.TemporaryDirectory(prefix=".doctor_", dir=str(runs_dir)) as tmp:
            run_dir = Path(tmp)
            spec = normalize_run_spec(payload, workspace, run_dir, run_id="doctor")
            materialize_template_strategy(spec)
            checks = build_preflight(spec, runs_dir)
    except (OSError, StudioValidationError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"FAIL CLI configuration: {exc}")
        return 1

    failures = [check for check in checks if check["status"] == "fail"]
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failures,
                    "workspace": str(workspace),
                    "runs_dir": str(runs_dir),
                    "checks": checks,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Lumibot doctor: {workspace}")
        for check in checks:
            print(f"{check['status'].upper():4} {check['title']}: {check['detail']}")
    return 1 if failures else 0
