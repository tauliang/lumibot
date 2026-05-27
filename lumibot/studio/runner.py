"""Subprocess entry point for executing one Studio backtest run."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("Usage: python -m lumibot.studio.runner /path/to/run.json", file=sys.stderr)
        return 2
    spec_path = Path(argv[0]).resolve()
    try:
        spec = _read_spec(spec_path)
        _run_spec(spec, spec_path.parent)
        return 0
    except KeyboardInterrupt:
        print("Backtest canceled.", file=sys.stderr)
        return 130
    except Exception:
        traceback.print_exc()
        return 1


def _read_spec(spec_path: Path) -> dict:
    with spec_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_spec(spec: dict, run_dir: Path) -> None:
    # These must be set before importing most Lumibot modules because credentials.py
    # reads environment variables at import time.
    os.environ["IS_BACKTESTING"] = "true"
    os.environ["BACKTESTING_DATA_SOURCE"] = "none"
    os.environ["BACKTESTING_START"] = spec["backtest"]["start"]
    os.environ["BACKTESTING_END"] = spec["backtest"]["end"]
    os.environ["BACKTESTING_BUDGET"] = str(spec["backtest"]["budget"])
    os.environ["LOG_BACKTEST_PROGRESS_TO_FILE"] = "true"
    os.environ["BACKTESTING_SHOW_PROGRESS_BAR"] = "false"
    os.environ["BACKTESTING_QUIET_LOGS"] = "false"
    os.environ.setdefault("LUMIBOT_DISABLE_DOTENV_LOCAL", "1")

    from lumibot.backtesting import PandasDataBacktesting, YahooDataBacktesting
    from lumibot.entities import Asset, Data

    strategy_class = _load_strategy_class(
        Path(spec["strategy"]["path"]),
        spec["strategy"]["class_name"],
    )
    data_source_type = spec["data_source"]["type"]
    pandas_data = None
    datasource_class = YahooDataBacktesting
    if data_source_type == "pandas_csv":
        datasource_class = PandasDataBacktesting
        pandas_data = _load_csv_data(spec, Asset, Data)
    elif data_source_type != "yahoo":
        raise ValueError(f"Unsupported Studio data source: {data_source_type}")

    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    outputs = spec.get("outputs") or {}
    backtest = spec["backtest"]
    benchmark = backtest.get("benchmark_asset") or None
    risk_free_rate = backtest.get("risk_free_rate")
    parameters = dict(spec.get("parameters") or {})
    symbol = spec.get("data_source", {}).get("symbol")
    if symbol and "symbol" not in parameters:
        parameters["symbol"] = symbol

    print(f"Starting Studio backtest {spec['run_id']}")
    print(f"Strategy: {spec['strategy']['class_name']}")
    print(f"Data source: {data_source_type}")
    print(f"Window: {backtest['start']} -> {backtest['end']}")

    strategy_class.backtest(
        datasource_class=datasource_class,
        backtesting_start=datetime.fromisoformat(backtest["start"]),
        backtesting_end=datetime.fromisoformat(backtest["end"]),
        budget=float(backtest["budget"]),
        benchmark_asset=benchmark,
        risk_free_rate=risk_free_rate,
        parameters=parameters,
        pandas_data=pandas_data,
        stats_file=str(artifacts_dir / "stats.csv"),
        plot_file_html=str(artifacts_dir / "trades.html"),
        trades_file=str(artifacts_dir / "trades.csv"),
        settings_file=str(artifacts_dir / "settings.json"),
        indicators_file=str(artifacts_dir / "indicators.html"),
        tearsheet_file=str(artifacts_dir / "tearsheet.html"),
        tearsheet_metrics_file=str(artifacts_dir / "tearsheet_metrics.json"),
        show_plot=bool(outputs.get("show_plot", True)),
        show_indicators=bool(outputs.get("show_indicators", True)),
        show_tearsheet=False,
        save_tearsheet=bool(outputs.get("save_tearsheet", True)),
        save_logfile=bool(outputs.get("save_logfile", False)),
        logfile=str(artifacts_dir / "logs.csv") if outputs.get("save_logfile") else None,
        show_progress_bar=False,
        quiet_logs=False,
    )
    print("Studio backtest completed.")


def _load_strategy_class(path: Path, class_name: str):
    if not path.exists():
        raise FileNotFoundError(f"Strategy file does not exist: {path}")
    module_name = f"_lumibot_studio_strategy_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import strategy file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        strategy_class = getattr(module, class_name)
    except AttributeError as exc:
        raise AttributeError(f"Strategy class {class_name!r} was not found in {path}") from exc
    return strategy_class


def _load_csv_data(spec: dict, Asset, Data) -> dict:
    import pandas as pd

    data_source = spec["data_source"]
    csv_path = Path(data_source["csv_path"])
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")
    df = pd.read_csv(csv_path)
    datetime_column = data_source.get("datetime_column") or "datetime"
    if datetime_column not in df.columns:
        candidates = ["datetime", "date", "timestamp", "time", "Date", "Timestamp"]
        datetime_column = next((column for column in candidates if column in df.columns), None)
    if datetime_column is None:
        raise ValueError("CSV must include a datetime/date/timestamp column")
    df[datetime_column] = pd.to_datetime(df[datetime_column])
    df = df.set_index(datetime_column).sort_index()
    rename = {column: str(column).strip().lower() for column in df.columns}
    df = df.rename(columns=rename)
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required OHLCV columns: {missing}")
    symbol = data_source.get("symbol") or "CSV"
    asset = Asset(symbol, Asset.AssetType.STOCK)
    timezone = data_source.get("timezone") or None
    if getattr(df.index, "tz", None) is not None:
        timezone = None
    return {asset: Data(asset, df[required], timestep="day", timezone=timezone)}


if __name__ == "__main__":
    raise SystemExit(main())
