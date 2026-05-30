"""Command line entry point for LumiBot operator tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lumibot.runtime import BacktestRunConfig, LiveRunConfig, RunController, RunEvent


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "tui":
        return _run_tui(args)
    if args.command == "backtest":
        config = BacktestRunConfig(
            script=Path(args.script),
            cwd=Path(args.cwd) if args.cwd else None,
            start=args.start,
            end=args.end,
            data_source=args.data_source,
            budget=args.budget,
            show_progress=args.show_progress,
            env=_parse_env(args.env),
        )
        return _run_config(config, json_output=args.json)
    if args.command == "run-live":
        config = LiveRunConfig(
            script=Path(args.script),
            cwd=Path(args.cwd) if args.cwd else None,
            once=args.once,
            env=_parse_env(args.env),
        )
        return _run_config(config, json_output=args.json)

    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lumibot", description="LumiBot local operator tools")
    subparsers = parser.add_subparsers(dest="command")

    tui = subparsers.add_parser("tui", help="Open the optional terminal operator console")
    tui.add_argument("--script", help="Optional strategy script to prefill in the console")
    tui.add_argument("--cwd", help="Working directory for the optional strategy script")

    backtest = subparsers.add_parser("backtest", help="Run a strategy script in backtesting mode")
    _add_script_args(backtest)
    backtest.add_argument("--start", help="Backtest start date or datetime")
    backtest.add_argument("--end", help="Backtest end date or datetime")
    backtest.add_argument("--data-source", help="BACKTESTING_DATA_SOURCE override, e.g. none, yahoo, thetadata")
    backtest.add_argument("--budget", help="BACKTESTING_BUDGET override")
    backtest.add_argument("--show-progress", action="store_true", help="Show legacy progress bar output")
    backtest.add_argument("--json", action="store_true", help="Emit runtime events as JSON lines")

    live = subparsers.add_parser("run-live", help="Run a live strategy script")
    _add_script_args(live)
    live.add_argument("--once", action=argparse.BooleanOptionalAction, default=True, help="Run one scheduled live tick")
    live.add_argument("--json", action="store_true", help="Emit runtime events as JSON lines")

    return parser


def _add_script_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--script", required=True, help="Strategy Python file to execute")
    parser.add_argument("--cwd", help="Working directory for the child process")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra environment variable for the child process; may be repeated",
    )


def _run_tui(args: argparse.Namespace) -> int:
    try:
        from lumibot.tui.app import run_tui
    except ImportError as exc:
        print(
            "The LumiBot TUI requires optional dependencies. Install with: pip install \"lumibot[tui]\"",
            file=sys.stderr,
        )
        print(f"Missing dependency detail: {exc}", file=sys.stderr)
        return 2

    run_tui(script=args.script, cwd=args.cwd)
    return 0


def _run_config(config, *, json_output: bool) -> int:
    handle = RunController().start(config)
    exit_code = 0
    for event in handle.events():
        if json_output:
            print(json.dumps(event.to_dict(), sort_keys=True))
        else:
            print(_format_event(event))
        if event.type == "failed":
            exit_code = int(getattr(event, "returncode", 1) or 1)
    return exit_code


def _format_event(event: RunEvent) -> str:
    if event.type == "started":
        return f"[{event.run_id}] started pid={getattr(event, 'pid', '')}"
    if event.type == "progress":
        percent = getattr(event, "percent", None)
        progress = "" if percent is None else f"{percent:.2f}%"
        return f"[{event.run_id}] progress {progress} {getattr(event, 'simulation_date', '')}".rstrip()
    if event.type == "log":
        stream = getattr(event, "stream", "stdout")
        return f"[{event.run_id}] {stream}: {getattr(event, 'line', '')}"
    if event.type == "artifact":
        return f"[{event.run_id}] artifact {getattr(event, 'artifact_type', 'file')}: {getattr(event, 'path', '')}"
    if event.type == "finished":
        return f"[{event.run_id}] finished returncode={getattr(event, 'returncode', 0)}"
    if event.type == "failed":
        return f"[{event.run_id}] failed returncode={getattr(event, 'returncode', '')}: {getattr(event, 'message', '')}"
    return f"[{event.run_id}] {event.type}"


def _parse_env(items: list[str]) -> dict[str, str]:
    env = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--env must be KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit("--env key cannot be empty")
        env[key] = value
    return env


if __name__ == "__main__":
    raise SystemExit(main())
