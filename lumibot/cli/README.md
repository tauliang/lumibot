# Lumibot Local CLI Tools

This folder contains the local CLI workflow for beginner backtesting:

- `lumibot init` creates a small local project.
- `lumibot doctor` checks that the project can run.
- `lumibot run` executes one isolated backtest subprocess and writes artifacts.
- `lumibot studio` opens the browser-based local Studio.

The default workflow does not need broker credentials. Yahoo runs use daily stock/ETF data. CSV runs use local OHLCV files with `datetime`, `open`, `high`, `low`, `close`, and `volume` columns.

## Quickstart: Yahoo Stock/ETF Backtest

```bash
lumibot init my-backtest --template buy_and_hold --symbol NVDA --start 2013-01-02 --end 2024-12-31
cd my-backtest
lumibot doctor
lumibot run
```

Outputs are written to `runs/<run_id>/`:

- `run.json`: normalized RunSpec.
- `status.json`: final RunStatus, metrics, artifacts, and errors.
- `output.log`: redacted subprocess logs.
- `artifacts/`: Lumibot stats, trades, settings, plots, indicators, and tearsheets when enabled.

## Quickstart: No-Network CSV Backtest

```bash
lumibot init csv-backtest --data-source csv --symbol SPY --start 2024-01-02 --end 2024-01-10
cd csv-backtest
lumibot doctor
lumibot run --json
```

The scaffold includes `data/sample.csv`, so this path can run without API keys or network data.

## Run From CLI Options

```bash
lumibot run \
  --strategy strategies/strategy.py \
  --class StudioCsvSingleSymbol \
  --data-source csv \
  --csv data/sample.csv \
  --symbol SPY \
  --start 2024-01-02 \
  --end 2024-01-10 \
  --budget 100000 \
  --benchmark SPY \
  --no-plot \
  --no-indicators \
  --no-tearsheet
```

Use `--param KEY=VALUE` for strategy parameters:

```bash
lumibot run --param target_cash_pct=0.05 --param symbol=SPY
```

## Project Config

`lumibot.toml` is the default config file:

```toml
[project]
name = "csv-backtest"
runs_dir = "runs"

[strategy]
source = "file"
path = "strategies/strategy.py"
class_name = "StudioCsvSingleSymbol"
template_id = "csv_single_symbol"

[data_source]
type = "pandas_csv"
symbol = "SPY"
csv_path = "data/sample.csv"
datetime_column = "datetime"
timezone = "America/New_York"

[backtest]
start = "2024-01-02"
end = "2024-01-10"
budget = 100000.0
benchmark_asset = "SPY"

[parameters]
symbol = "SPY"
target_cash_pct = 0.02

[outputs]
show_plot = false
show_indicators = false
save_tearsheet = false
save_logfile = false
```

CLI flags override config values for a single command.

## Doctor Checks

`lumibot doctor` validates Python, Lumibot imports, run directory writability, dates, data-source compatibility, benchmark settings, strategy class discovery, and static strategy warnings such as `datetime.now()` or `date.today()`.

Exit codes:

- `0`: checks passed.
- `1`: one or more checks failed.
- `2`: CLI/config input could not be parsed.

## Run Behavior

`lumibot run` creates one run directory and starts `python -m lumibot.studio.runner` in a subprocess. Strategy code never runs inside the CLI process. Logs are redacted for common secret names such as `API_KEY`, `SECRET`, `TOKEN`, and `PASSWORD`.

Exit codes:

- `0`: backtest completed.
- `1`: subprocess failed or run was canceled.
- `2`: preflight or CLI input failed before the subprocess started.
