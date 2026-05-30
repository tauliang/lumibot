"""Textual-based local operator console for LumiBot."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Log, Static, TabbedContent, TabPane

from lumibot.runtime import BacktestRunConfig, LiveRunConfig, RunController, RunEvent, RunHandle
from lumibot.runtime.redaction import redact_mapping


def run_tui(script: str | None = None, cwd: str | None = None) -> None:
    LumibotTuiApp(initial_script=script, initial_cwd=cwd).run()


class LumibotTuiApp(App):
    """Local LumiBot operator console."""

    TITLE = "LumiBot Operator Console"
    SUB_TITLE = "Local backtests, live ticks, logs, artifacts, and agent traces"
    BINDINGS = [
        ("b", "start_backtest", "Backtest"),
        ("l", "start_live_once", "Live once"),
        ("s", "stop_selected", "Stop"),
        ("f", "focus_filter", "Filter logs"),
        ("c", "copy_replay_command", "Replay command"),
        ("o", "open_selected_artifact", "Artifact path"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #top {
        height: 5;
        padding: 0 1;
        border-bottom: solid $primary;
    }

    #workspace {
        height: 1fr;
    }

    #runs-panel {
        width: 28;
        border-right: solid $primary;
        padding: 0 1;
    }

    #center-panel {
        width: 1fr;
        min-width: 50;
        padding: 0 1;
    }

    #inspector-panel {
        width: 45;
        border-left: solid $primary;
        padding: 0 1;
    }

    #log {
        height: 1fr;
        border: solid $surface;
    }

    DataTable {
        height: 1fr;
    }

    #progress {
        height: 6;
        border: solid $surface;
        padding: 1;
    }
    """

    def __init__(self, *, initial_script: str | None = None, initial_cwd: str | None = None) -> None:
        super().__init__()
        self.initial_script = initial_script or ""
        self.initial_cwd = initial_cwd or ""
        self.controller = RunController()
        self.handles: dict[str, RunHandle] = {}
        self.selected_run_id: str | None = None
        self.latest_config: dict[str, Any] = {}
        self.latest_artifact_path: str | None = None
        self.log_filter = ""
        self._run_rows: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="top"):
            yield Label("Strategy script")
            with Horizontal():
                yield Input(value=self.initial_script, placeholder="examples/my_strategy.py", id="script-input")
                yield Input(value=self.initial_cwd, placeholder="working directory (optional)", id="cwd-input")
                yield Button("Backtest", id="backtest-button", variant="success")
                yield Button("Live Once", id="live-button", variant="primary")
                yield Button("Stop", id="stop-button", variant="error")
        with Horizontal(id="workspace"):
            with Vertical(id="runs-panel"):
                yield Label("Runs")
                yield DataTable(id="runs")
            with Vertical(id="center-panel"):
                yield Static("No run selected", id="progress")
                yield Label("Logs")
                yield Input(placeholder="filter logs", id="log-filter")
                yield Log(id="log", auto_scroll=True)
            with Vertical(id="inspector-panel"):
                with TabbedContent():
                    with TabPane("Orders"):
                        yield DataTable(id="orders")
                    with TabPane("Positions"):
                        yield DataTable(id="positions")
                    with TabPane("Artifacts"):
                        yield DataTable(id="artifacts")
                    with TabPane("Agents"):
                        yield DataTable(id="agents")
                    with TabPane("Config"):
                        yield DataTable(id="config")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table("runs", ("Run", "Kind", "Status", "Progress"))
        self._setup_table("orders", ("Field", "Value"))
        self._setup_table("positions", ("Field", "Value"))
        self._setup_table("artifacts", ("Type", "Name", "Path"))
        self._setup_table("agents", ("Name", "Path", "Summary"))
        self._setup_table("config", ("Key", "Value"))
        self.query_one("#runs", DataTable).cursor_type = "row"
        if self.initial_script:
            self.action_start_backtest()

    def _setup_table(self, table_id: str, columns: tuple[str, ...]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        for column in columns:
            table.add_column(column, key=column)
        table.zebra_stripes = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "backtest-button":
            self.action_start_backtest()
        elif event.button.id == "live-button":
            self.action_start_live_once()
        elif event.button.id == "stop-button":
            self.action_stop_selected()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log-filter":
            self.log_filter = event.value.strip().lower()

    def action_focus_filter(self) -> None:
        self.query_one("#log-filter", Input).focus()

    def action_start_backtest(self) -> None:
        script = self._script_value()
        if not script:
            self.notify("Enter a strategy script first", severity="warning")
            return
        config = BacktestRunConfig(script=Path(script), cwd=self._cwd_value())
        self._start_run(config)

    def action_start_live_once(self) -> None:
        script = self._script_value()
        if not script:
            self.notify("Enter a strategy script first", severity="warning")
            return
        config = LiveRunConfig(script=Path(script), cwd=self._cwd_value(), once=True)
        self._start_run(config)

    def action_stop_selected(self) -> None:
        if self.selected_run_id and self.selected_run_id in self.handles:
            self.handles[self.selected_run_id].stop()
            self._append_log("runtime", f"Stop requested for {self.selected_run_id}")

    def action_copy_replay_command(self) -> None:
        if not self.selected_run_id:
            return
        config = self.latest_config.get(self.selected_run_id) or {}
        script = config.get("script", "")
        command = f"lumibot backtest --script {script}" if script else ""
        if command:
            self._append_log("runtime", f"Replay command: {command}")

    def action_open_selected_artifact(self) -> None:
        if self.latest_artifact_path:
            self._append_log("runtime", f"Artifact path: {self.latest_artifact_path}")

    def _script_value(self) -> str:
        return self.query_one("#script-input", Input).value.strip()

    def _cwd_value(self) -> Path | None:
        value = self.query_one("#cwd-input", Input).value.strip()
        return Path(value) if value else None

    def _start_run(self, config) -> None:
        try:
            handle = self.controller.start(config)
        except Exception as exc:
            self.notify(f"Could not start run: {exc}", severity="error")
            return
        self.handles[handle.run_id] = handle
        self.selected_run_id = handle.run_id
        self.latest_config[handle.run_id] = config.display_config()
        self._upsert_run(handle.run_id, config.kind, "running", "")
        self._populate_config(config.display_config())
        thread = threading.Thread(target=self._consume_events, args=(handle,), daemon=True)
        thread.start()

    def _consume_events(self, handle: RunHandle) -> None:
        for event in handle.events():
            self.call_from_thread(self._handle_event, event)

    def _handle_event(self, event: RunEvent) -> None:
        self.selected_run_id = event.run_id
        if event.type == "started":
            self._upsert_run(event.run_id, getattr(event, "config", {}).get("kind", ""), "running", "")
        elif event.type == "progress":
            percent = getattr(event, "percent", None)
            progress = "" if percent is None else f"{percent:.2f}%"
            self._upsert_run(event.run_id, self._run_kind(event.run_id), "running", progress)
            self.query_one("#progress", Static).update(self._progress_text(event))
        elif event.type == "log":
            self._append_log(getattr(event, "stream", "stdout"), getattr(event, "line", ""))
        elif event.type == "order":
            self._replace_key_value_table("orders", getattr(event, "order", {}))
        elif event.type == "position":
            self._replace_key_value_table("positions", getattr(event, "position", {}))
        elif event.type == "artifact":
            self.latest_artifact_path = getattr(event, "path", "")
            table = self.query_one("#artifacts", DataTable)
            table.add_row(getattr(event, "artifact_type", "file"), getattr(event, "name", ""), getattr(event, "path", ""))
        elif event.type == "agent_trace":
            table = self.query_one("#agents", DataTable)
            table.add_row(getattr(event, "name", ""), getattr(event, "path", ""), getattr(event, "summary", ""))
        elif event.type == "finished":
            self._upsert_run(event.run_id, self._run_kind(event.run_id), "finished", "100.00%")
        elif event.type == "failed":
            self._upsert_run(event.run_id, self._run_kind(event.run_id), "failed", "")
            self._append_log("runtime", getattr(event, "message", "Run failed"))

    def _upsert_run(self, run_id: str, kind: str, status: str, progress: str) -> None:
        table = self.query_one("#runs", DataTable)
        key = run_id
        row = (run_id, kind, status, progress)
        if key in self._run_rows:
            table.update_cell(key, "Run", row[0])
            table.update_cell(key, "Kind", row[1])
            table.update_cell(key, "Status", row[2])
            table.update_cell(key, "Progress", row[3])
        else:
            table.add_row(*row, key=key)
            self._run_rows.add(key)

    def _run_kind(self, run_id: str) -> str:
        return str((self.latest_config.get(run_id) or {}).get("kind") or "")

    def _append_log(self, stream: str, line: str) -> None:
        if self.log_filter and self.log_filter not in line.lower():
            return
        self.query_one("#log", Log).write_line(f"{stream}: {line}")

    def _progress_text(self, event: RunEvent) -> str:
        lines = [
            f"Run: {event.run_id}",
            f"Simulation: {getattr(event, 'simulation_date', '')}",
            f"Progress: {getattr(event, 'percent', '')}",
            f"Portfolio: {getattr(event, 'portfolio_value', '')}",
            f"Cash: {getattr(event, 'cash', '')}",
            f"ETA: {getattr(event, 'eta', '')}",
        ]
        download_status = getattr(event, "download_status", None)
        if download_status:
            lines.append(f"Download: {json.dumps(redact_mapping(download_status), sort_keys=True)}")
        return "\n".join(lines)

    def _populate_config(self, config: dict[str, Any]) -> None:
        self._replace_key_value_table("config", redact_mapping(config))

    def _replace_key_value_table(self, table_id: str, payload: dict[str, Any]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear()
        for key, value in sorted((payload or {}).items()):
            if isinstance(value, (dict, list)):
                value_text = json.dumps(redact_mapping(value) if isinstance(value, dict) else value, sort_keys=True)
            else:
                value_text = str(value)
            table.add_row(str(key), value_text)
