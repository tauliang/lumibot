# Runtime TUI

> Local runtime events, CLI commands, and the optional Textual operator console.

**Last Updated:** 2026-05-30
**Status:** Active
**Audience:** Developers + AI Agents

## Overview

LumiBot now has a small stdlib-only runtime layer for local operator tooling:

- `lumibot.runtime.RunController` launches a strategy script in a child process.
- `RunHandle.events()` yields typed events for starts, logs, progress, orders, positions, artifacts, agent traces, finishes, and failures.
- `lumibot.cli` exposes `lumibot backtest`, `lumibot run-live`, and `lumibot tui`.
- `lumibot.tui` is optional and only imports Textual/Rich when the TUI is launched.

This is intentionally incremental. The existing `Trader`, `Strategy`, `StrategyExecutor`, brokers, data sources, progress CSV, and artifact generation remain the source of trading behavior.

## Public Commands

```bash
pip install "lumibot[tui]"
lumibot tui

lumibot backtest \
  --script examples/my_strategy.py \
  --start 2025-01-01 \
  --end 2025-02-01 \
  --data-source none \
  --budget 100000

lumibot run-live --script examples/my_strategy.py --once
```

Use `--json` with `backtest` or `run-live` to emit one JSON event per line for scripts and automation.

## Runtime Contract

The runtime controller runs strategy files as child processes. It does not import the strategy module into the operator process. This keeps crashes, signal handling, broker SDK side effects, and environment loading isolated from the CLI/TUI process.

Backtest runs set:

- `IS_BACKTESTING=true`
- `LOG_BACKTEST_PROGRESS_TO_FILE=true`
- `BACKTESTING_START`, `BACKTESTING_END`, `BACKTESTING_DATA_SOURCE`, and `BACKTESTING_BUDGET` when passed

Live one-shot runs set:

- `LUMIBOT_SCHEDULED_EXECUTION=true`

The controller watches `logs/progress.csv` under the run working directory and converts rows into typed progress/order/position events. When the child exits, files under `logs/` are emitted as artifact events.

## Safety

The runtime and TUI redact config/env keys containing:

- `key`
- `token`
- `secret`
- `password`
- `auth`

Do not display raw environment dictionaries directly in new CLI/TUI surfaces. Use `lumibot.runtime.redact_mapping()`.

## Testing

Focused tests:

```bash
python -m pytest -q \
  tests/test_runtime_events.py \
  tests/test_cli.py \
  tests/test_packaging_metadata.py \
  tests/test_lazy_exports.py
```

Build smoke:

```bash
python -m build --wheel --sdist
```
