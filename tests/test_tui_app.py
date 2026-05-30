from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, Input, Log

from lumibot.runtime import RunArtifactEvent, RunLogEvent, RunProgressEvent, RunStartedEvent
from lumibot.tui.app import LumibotTuiApp


def test_tui_updates_tables_and_filters_logs():
    asyncio.run(_exercise_tui())


async def _exercise_tui():
    app = LumibotTuiApp()

    async with app.run_test() as pilot:
        app._handle_event(RunStartedEvent(run_id="run-1", config={"kind": "backtest"}))
        app._handle_event(RunProgressEvent(run_id="run-1", percent=12.5, simulation_date="2025-01-02"))
        app._handle_event(RunArtifactEvent(run_id="run-1", path="/tmp/trades.csv", name="trades.csv", artifact_type="trades"))

        runs = app.query_one("#runs", DataTable)
        artifacts = app.query_one("#artifacts", DataTable)
        assert runs.row_count == 1
        assert artifacts.row_count == 1

        await pilot.press("f")
        assert app.query_one("#log-filter", Input).has_focus

        app.log_filter = "keep"
        app._handle_event(RunLogEvent(run_id="run-1", stream="stdout", line="drop this"))
        app._handle_event(RunLogEvent(run_id="run-1", stream="stdout", line="keep this"))
        assert "keep this" in app.query_one("#log", Log).lines[-1]
