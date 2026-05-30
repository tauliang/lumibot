"""Run configuration objects for local LumiBot operator tooling."""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .redaction import redact_mapping


@dataclass(slots=True)
class RunConfig:
    script: Path
    cwd: Path | None = None
    python: str = sys.executable
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    log_dir: Path | None = None

    kind: str = "script"

    def __post_init__(self) -> None:
        self.script = Path(self.script).expanduser()
        if self.cwd is not None:
            self.cwd = Path(self.cwd).expanduser()
        if self.log_dir is not None:
            self.log_dir = Path(self.log_dir).expanduser()

    @property
    def resolved_cwd(self) -> Path:
        if self.cwd is not None:
            return self.cwd
        if self.script.parent != Path(""):
            return self.script.parent
        return Path.cwd()

    @property
    def resolved_log_dir(self) -> Path:
        return self.log_dir or (self.resolved_cwd / "logs")

    @property
    def progress_csv_path(self) -> Path:
        return self.resolved_log_dir / "progress.csv"

    def build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update({key: str(value) for key, value in self.env.items()})
        return env

    def command(self) -> list[str]:
        return [self.python, str(self.script), *self.args]

    def display_config(self) -> dict[str, Any]:
        return redact_mapping(
            {
                "kind": self.kind,
                "script": str(self.script),
                "cwd": str(self.resolved_cwd),
                "log_dir": str(self.resolved_log_dir),
                "env": self.env,
                "args": self.args,
            }
        )


@dataclass(slots=True)
class BacktestRunConfig(RunConfig):
    start: str | None = None
    end: str | None = None
    data_source: str | None = None
    budget: str | float | int | None = None
    show_progress: bool = False

    kind: str = "backtest"

    def build_env(self) -> dict[str, str]:
        env = RunConfig.build_env(self)
        env.setdefault("IS_BACKTESTING", "true")
        env.setdefault("LOG_BACKTEST_PROGRESS_TO_FILE", "true")
        env.setdefault("BACKTESTING_SHOW_PROGRESS_BAR", "true" if self.show_progress else "false")
        if self.start:
            env["BACKTESTING_START"] = str(self.start)
        if self.end:
            env["BACKTESTING_END"] = str(self.end)
        if self.data_source:
            env["BACKTESTING_DATA_SOURCE"] = str(self.data_source)
        if self.budget is not None:
            env["BACKTESTING_BUDGET"] = str(self.budget)
        return env

    def display_config(self) -> dict[str, Any]:
        payload = RunConfig.display_config(self)
        payload.update(
            {
                "start": self.start,
                "end": self.end,
                "data_source": self.data_source,
                "budget": self.budget,
                "show_progress": self.show_progress,
            }
        )
        return redact_mapping(payload)


@dataclass(slots=True)
class LiveRunConfig(RunConfig):
    once: bool = True

    kind: str = "live"

    def build_env(self) -> dict[str, str]:
        env = RunConfig.build_env(self)
        if self.once:
            env["LUMIBOT_SCHEDULED_EXECUTION"] = "true"
        return env

    def display_config(self) -> dict[str, Any]:
        payload = RunConfig.display_config(self)
        payload["once"] = self.once
        return redact_mapping(payload)
