# Local Backtest Studio

The Local Backtest Studio is a beginner-focused web UI for running LumiBot
backtests on a local machine. It is launched with:

```bash
lumibot studio
```

The MVP is intentionally local-only. It helps users run no-key Yahoo stock/ETF
backtests or local CSV-backed backtests, inspect generated artifacts, review
metrics, and diagnose failures without setting up broker credentials or a cloud
account.

## What Was Added

The Studio implementation is split into small modules:

| File | Purpose |
| --- | --- |
| `lumibot/cli.py` | Adds the `lumibot studio` command. |
| `studio/app.py` | Flask app, local API, and bundled single-page UI. |
| `studio/manager.py` | Run queue, subprocess orchestration, cancellation, and status persistence. |
| `studio/runner.py` | Subprocess entry point that imports and runs one backtest. |
| `studio/models.py` | RunSpec normalization, validation, preflight checks, and strategy discovery. |
| `studio/templates.py` | Built-in beginner strategy templates. |
| `studio/artifacts.py` | Artifact indexing, metrics extraction, chart data, CSV previews, and log redaction. |
| `tests/test_studio.py` | Unit and integration coverage for the Studio MVP. |

`setup.py` also registers the console script:

```python
entry_points={
    "console_scripts": [
        "lumibot=lumibot.cli:main",
    ],
}
```

## Quick Start

From a local LumiBot checkout:

```bash
pip install -e .
lumibot studio
```

Default launch behavior:

```bash
lumibot studio \
  --host 127.0.0.1 \
  --port 8765 \
  --workspace "$(pwd)" \
  --open
```

The default runs directory is:

```text
<workspace>/.lumibot/studio/runs
```

To keep the browser closed:

```bash
lumibot studio --no-open
```

## MVP Scope

Included:

- Local Flask web app.
- One subprocess per backtest.
- One active run at a time; additional runs are queued.
- Built-in templates.
- User strategy file discovery.
- Yahoo daily stock/ETF backtests.
- Local CSV/Pandas backtests.
- Live run status, progress, logs, and cancellation.
- Results view with metrics, charts, trades, logs, HTML artifacts, and downloads.
- History view with prior runs.
- Preflight checks and common static warnings.
- Secret redaction for common key names.

Out of scope for the MVP:

- Live trading.
- Paper trading.
- Broker credential management.
- Paid data-provider setup.
- AI strategy authoring.
- Multi-user auth.
- Cloud sync or deployment.
- Docker isolation.
- Full code editing.

## User Workflow

1. Launch `lumibot studio`.
2. Choose a built-in template or select a local Python strategy file.
3. Choose Yahoo or Pandas/CSV data.
4. Set symbol, date range, budget, benchmark, and parameters.
5. Run preflight checks.
6. Start the backtest.
7. Watch progress and logs.
8. Inspect metrics, charts, trades, tearsheet, settings, and raw artifacts.
9. Rerun or open prior runs from History.

## Built-In Templates

| Template ID | Class | Purpose |
| --- | --- | --- |
| `buy_and_hold` | `StudioBuyAndHold` | Buy one stock or ETF on the first trading day and hold it. |
| `moving_average_crossover` | `StudioMovingAverageCrossover` | Buy when fast MA is above slow MA; sell when it falls below. |
| `portfolio_rebalance` | `StudioPortfolioRebalance` | Equal-weight a comma-separated basket on a fixed cadence. |
| `csv_single_symbol` | `StudioCsvSingleSymbol` | Buy one symbol using local OHLCV CSV data. |

Template strategies are materialized into each run directory as `strategy.py`.
This keeps every run reproducible even if the template changes later.

## Data Sources

### Yahoo

Yahoo is the default beginner path. It requires no credentials and is intended
for daily stock and ETF backtests.

Studio explicitly warns users that Yahoo is not intended for:

- Intraday backtests.
- Options.
- Futures.
- High-fidelity execution modeling.

### Pandas/CSV

CSV input requires OHLCV columns:

```text
datetime,open,high,low,close,volume
```

The datetime column defaults to `datetime`, but the runner also recognizes
common alternatives such as `date`, `timestamp`, `time`, `Date`, and
`Timestamp`.

CSV data is loaded into LumiBot's `PandasDataBacktesting` path with a stock
`Asset` using the selected symbol.

## Run Execution

The Studio web process never runs user strategy code in-process. Each run is
executed with:

```bash
python -m lumibot.studio.runner <run_dir>/run.json
```

Benefits:

- A strategy exception does not crash the Studio server.
- stdout and stderr are captured in `output.log`.
- Exit code and failure summary are persisted.
- Each run gets an isolated directory.

The runner calls `Strategy.backtest(...)` with explicit artifact paths:

- `stats_file`
- `plot_file_html`
- `trades_file`
- `settings_file`
- `indicators_file`
- `tearsheet_file`
- `tearsheet_metrics_file`

It also sets backtesting environment variables for the subprocess, including:

- `IS_BACKTESTING=true`
- `BACKTESTING_DATA_SOURCE=none`
- `BACKTESTING_START`
- `BACKTESTING_END`
- `BACKTESTING_BUDGET`
- `LOG_BACKTEST_PROGRESS_TO_FILE=true`

## Run Directory Layout

Each run is stored under:

```text
<runs-dir>/<run_id>/
```

Typical contents:

```text
run.json
status.json
output.log
strategy.py
logs/
  progress.csv
artifacts/
  stats.csv
  trades.csv
  trade_events.csv
  settings.json
  trades.html
  indicators.html
  tearsheet.html
  tearsheet.csv
  tearsheet_metrics.json
```

Some artifacts may be absent depending on run settings, strategy behavior, and
whether post-processing succeeds.

## RunSpec Schema

The Studio persists every requested run as `run.json`.

```json
{
  "schema_version": 1,
  "run_id": "run_20260527_193143_28ee9c17",
  "workspace": "/path/to/workspace",
  "strategy": {
    "source": "template",
    "path": "/path/to/run/strategy.py",
    "class_name": "StudioBuyAndHold",
    "template_id": "buy_and_hold"
  },
  "data_source": {
    "type": "yahoo",
    "symbol": "SPY",
    "csv_path": "",
    "datetime_column": "datetime",
    "timezone": "America/New_York"
  },
  "backtest": {
    "start": "2024-01-01",
    "end": "2024-12-31",
    "budget": 100000.0,
    "benchmark_asset": "SPY",
    "risk_free_rate": null
  },
  "parameters": {
    "symbol": "SPY"
  },
  "outputs": {
    "show_plot": true,
    "show_indicators": true,
    "save_tearsheet": true,
    "save_logfile": false
  }
}
```

Supported strategy sources:

- `template`
- `file`

Supported data sources:

- `yahoo`
- `pandas_csv`

## RunStatus Schema

The Studio persists run state as `status.json`.

```json
{
  "schema_version": 1,
  "run_id": "run_20260527_193143_28ee9c17",
  "state": "completed",
  "progress_pct": 100.0,
  "phase": "completed",
  "current_datetime": "2024-12-31",
  "started_at": "2026-05-27T19:31:43",
  "ended_at": "2026-05-27T19:31:45",
  "exit_code": 0,
  "error_summary": null,
  "metrics_summary": {},
  "artifacts": []
}
```

Supported states:

- `queued`
- `running`
- `completed`
- `failed`
- `canceled`

## Local API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Studio health, workspace, and runs directory. |
| `GET` | `/api/templates` | Built-in template list. |
| `POST` | `/api/strategies/discover` | Discover Strategy subclasses in a Python file. |
| `POST` | `/api/preflight` | Validate a proposed run before submission. |
| `POST` | `/api/runs` | Create and queue a run. |
| `GET` | `/api/runs` | List persisted runs. |
| `GET` | `/api/runs/<run_id>` | Fetch one run's spec and status. |
| `POST` | `/api/runs/<run_id>/cancel` | Cancel a queued or running backtest. |
| `GET` | `/api/runs/<run_id>/logs` | Fetch redacted captured logs. |
| `GET` | `/api/runs/<run_id>/artifacts` | List artifacts for a run. |
| `GET` | `/api/runs/<run_id>/artifacts/<artifact_name>` | Download or view one artifact. |
| `GET` | `/api/runs/<run_id>/table/<artifact_name>` | Paginated CSV preview. |
| `GET` | `/api/runs/<run_id>/chart-data` | Equity and drawdown chart data from `stats.csv`. |

Artifact paths reject traversal attempts such as `../run.json`.

## Metrics and Artifacts

The Studio extracts metrics from generated LumiBot artifacts in this order:

1. `tearsheet_metrics.json`
2. `stats.csv`
3. `trades.csv`

Displayed metrics include:

- Total return.
- CAGR.
- Sharpe.
- Sortino.
- Volatility.
- Max drawdown.
- Win rate.
- Number of trades.
- Final portfolio value.
- Runtime.

If a run completes with zero trades, the Studio surfaces a warning in
`error_summary` rather than marking the run as failed.

## Preflight Checks

Preflight validates:

- Python version is 3.10 or newer.
- LumiBot imports.
- Runs directory is writable.
- Date range is valid.
- Benchmark is set.
- CSV file exists for CSV runs.
- Strategy file exists.
- Strategy class can be discovered.
- Yahoo limitations are clearly shown.

Static warnings currently flag:

- `datetime.now(...)`
- `date.today(...)`
- Missing benchmark configuration in the strategy file.

## Security Notes

This is a local developer tool, not a security sandbox.

The subprocess model protects the Studio server from ordinary strategy crashes,
but users are still executing trusted local Python code.

The Studio redacts common secret-looking values from captured logs and CSV table
previews when keys include:

- `API_KEY`
- `SECRET`
- `TOKEN`
- `PASSWORD`

## Tests

Run the focused Studio suite:

```bash
python3 -m pytest tests/test_studio.py -q
```

Coverage includes:

- CLI argument parsing.
- Template listing.
- Strategy discovery.
- RunSpec validation.
- Artifact indexing.
- Metrics extraction.
- Progress parsing.
- Secret redaction.
- Artifact path traversal rejection.
- Flask API integration.
- No-network CSV template backtest.
- Failing strategy diagnostics.

## Manual Smoke Test

```bash
python3 -m py_compile \
  lumibot/cli.py \
  lumibot/studio/__init__.py \
  lumibot/studio/app.py \
  lumibot/studio/artifacts.py \
  lumibot/studio/manager.py \
  lumibot/studio/models.py \
  lumibot/studio/runner.py \
  lumibot/studio/templates.py \
  tests/test_studio.py

python3 -m pytest tests/test_studio.py -q
lumibot studio --help
lumibot studio --no-open
```

Then open:

```text
http://127.0.0.1:8765
```

The first screen should show the usable Setup workflow with template, data
source, symbol, benchmark, date range, budget, parameters, Preflight, and Run
controls.

## Future Enhancements

Likely next steps:

- Add provider setup flows for Polygon, ThetaData, IBKR, and DataBento.
- Add richer parameter schemas for templates and strategy files.
- Add multi-run comparison.
- Add retained run cleanup policies.
- Add deeper lookahead-bias linting.
- Add optional browser tests for the full run workflow.
- Add paper/live trading views only after the local backtesting flow is mature.
