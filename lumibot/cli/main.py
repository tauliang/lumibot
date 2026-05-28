"""Top-level Lumibot CLI parser."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lumibot", description="Lumibot command line tools")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create a local Lumibot backtest project")
    init_parser.add_argument("path", nargs="?", default=".", help="Project directory to create. Defaults to current directory.")
    init_parser.add_argument(
        "--template",
        default=None,
        help="Built-in template id. Defaults to buy_and_hold for Yahoo or csv_single_symbol for CSV.",
    )
    init_parser.add_argument("--symbol", default="SPY", help="Primary stock/ETF symbol. Defaults to SPY.")
    init_parser.add_argument("--benchmark", default="SPY", help="Benchmark asset. Defaults to SPY.")
    init_parser.add_argument(
        "--data-source",
        choices=["yahoo", "csv", "pandas_csv"],
        default=None,
        help="Data source for the starter project. Defaults to yahoo.",
    )
    init_parser.add_argument("--csv", dest="csv_path", default=None, help="CSV path for CSV-backed projects.")
    init_parser.add_argument("--budget", default="100000", help="Starting cash. Defaults to 100000.")
    init_parser.add_argument("--start", default="2024-01-02", help="Backtest start date. Defaults to 2024-01-02.")
    init_parser.add_argument("--end", default="2024-12-31", help="Backtest end date. Defaults to 2024-12-31.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")

    run_parser = subparsers.add_parser("run", help="Run one local backtest from a config or CLI options")
    _add_project_arguments(run_parser)
    _add_strategy_arguments(run_parser)
    _add_data_arguments(run_parser)
    _add_backtest_arguments(run_parser)
    _add_output_arguments(run_parser)
    run_parser.add_argument("--json", action="store_true", help="Print the final run payload as JSON.")

    doctor_parser = subparsers.add_parser("doctor", help="Check whether a local backtest is ready to run")
    _add_project_arguments(doctor_parser)
    _add_strategy_arguments(doctor_parser)
    _add_data_arguments(doctor_parser)
    _add_backtest_arguments(doctor_parser)
    doctor_parser.add_argument(
        "--profile",
        choices=["beginner", "all"],
        default="beginner",
        help="Check profile. The MVP currently uses beginner checks for both profiles.",
    )
    doctor_parser.add_argument("--fix", action="store_true", help="Create missing local folders that can be safely created.")
    doctor_parser.add_argument("--json", action="store_true", help="Print checks as JSON.")

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

    if args.command == "init":
        from .init import init_command

        return init_command(args)
    if args.command == "run":
        from .run import run_command

        return run_command(args)
    if args.command == "doctor":
        from .doctor import doctor_command

        return doctor_command(args)
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


def _add_project_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="lumibot.toml", help="Project config file. Defaults to lumibot.toml.")
    parser.add_argument("--workspace", default=None, help="Workspace for relative paths. Defaults to the config directory.")
    parser.add_argument("--runs-dir", default=None, help="Directory for CLI run artifacts. Defaults to <workspace>/runs.")


def _add_strategy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strategy", dest="strategy_path", default=None, help="Python strategy file to run.")
    parser.add_argument("--class", dest="class_name", default=None, help="Strategy class name.")
    parser.add_argument("--template", default=None, help="Built-in template id to run.")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Strategy parameter override. May be repeated.",
    )


def _add_data_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-source", choices=["yahoo", "csv", "pandas_csv"], default=None, help="Data source.")
    parser.add_argument("--symbol", default=None, help="Primary stock/ETF symbol.")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Path to an OHLCV CSV file.")
    parser.add_argument("--datetime-column", default=None, help="CSV datetime column. Defaults to datetime.")
    parser.add_argument("--timezone", default=None, help="CSV timezone. Defaults to America/New_York.")


def _add_backtest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", default=None, help="Backtest start date.")
    parser.add_argument("--end", default=None, help="Backtest end date.")
    parser.add_argument("--budget", default=None, help="Starting cash.")
    parser.add_argument("--benchmark", dest="benchmark_asset", default=None, help="Benchmark asset.")
    parser.add_argument("--risk-free-rate", default=None, help="Risk-free rate for metrics.")


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    plot = parser.add_mutually_exclusive_group()
    plot.add_argument("--plot", dest="show_plot", action="store_true", default=None, help="Generate the HTML plot.")
    plot.add_argument("--no-plot", dest="show_plot", action="store_false", help="Skip the HTML plot.")
    indicators = parser.add_mutually_exclusive_group()
    indicators.add_argument("--indicators", dest="show_indicators", action="store_true", default=None, help="Generate indicators.")
    indicators.add_argument("--no-indicators", dest="show_indicators", action="store_false", help="Skip indicators.")
    tearsheet = parser.add_mutually_exclusive_group()
    tearsheet.add_argument("--tearsheet", dest="save_tearsheet", action="store_true", default=None, help="Save a tearsheet.")
    tearsheet.add_argument("--no-tearsheet", dest="save_tearsheet", action="store_false", help="Skip the tearsheet.")
    logfile = parser.add_mutually_exclusive_group()
    logfile.add_argument("--save-logfile", dest="save_logfile", action="store_true", default=None, help="Save Lumibot CSV logs.")
    logfile.add_argument("--no-logfile", dest="save_logfile", action="store_false", help="Skip Lumibot CSV logs.")


if __name__ == "__main__":
    raise SystemExit(main())
