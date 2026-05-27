"""Command line entry points for LumiBot."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lumibot", description="LumiBot command line tools")
    subparsers = parser.add_subparsers(dest="command")

    studio = subparsers.add_parser("studio", help="Launch the local backtest Studio")
    studio.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to 127.0.0.1.")
    studio.add_argument("--port", type=int, default=8765, help="Port to bind. Defaults to 8765.")
    studio.add_argument(
        "--workspace",
        default=str(Path.cwd()),
        help="Workspace directory for strategy paths. Defaults to the current directory.",
    )
    studio.add_argument(
        "--runs-dir",
        default=None,
        help="Directory for Studio runs. Defaults to <workspace>/.lumibot/studio/runs.",
    )
    studio_open = studio.add_mutually_exclusive_group()
    studio_open.add_argument("--open", dest="open_browser", action="store_true", default=True, help="Open a browser.")
    studio_open.add_argument("--no-open", dest="open_browser", action="store_false", help="Do not open a browser.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "studio":
        from lumibot.studio import run_studio

        run_studio(
            host=args.host,
            port=args.port,
            workspace=args.workspace,
            runs_dir=args.runs_dir,
            open_browser=args.open_browser,
        )
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
