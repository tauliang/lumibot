"""Typed event stream emitted by local LumiBot run controllers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from .redaction import redact_mapping


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RunEvent:
    run_id: str
    timestamp: str = field(default_factory=_now_iso)

    event_type: ClassVar[str] = "event"

    @property
    def type(self) -> str:
        return self.event_type

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = self.event_type
        return redact_mapping(payload)


@dataclass(slots=True)
class RunStartedEvent(RunEvent):
    command: list[str] = field(default_factory=list)
    cwd: str = ""
    pid: int | None = None
    config: dict[str, Any] = field(default_factory=dict)

    event_type: ClassVar[str] = "started"


@dataclass(slots=True)
class RunProgressEvent(RunEvent):
    percent: float | None = None
    elapsed: str = ""
    eta: str = ""
    portfolio_value: str = ""
    simulation_date: str = ""
    cash: str = ""
    total_return_pct: str = ""
    download_status: dict[str, Any] = field(default_factory=dict)

    event_type: ClassVar[str] = "progress"


@dataclass(slots=True)
class RunLogEvent(RunEvent):
    stream: str = "stdout"
    line: str = ""
    level: str | None = None

    event_type: ClassVar[str] = "log"


@dataclass(slots=True)
class RunOrderEvent(RunEvent):
    order: dict[str, Any] = field(default_factory=dict)

    event_type: ClassVar[str] = "order"


@dataclass(slots=True)
class RunPositionEvent(RunEvent):
    position: dict[str, Any] = field(default_factory=dict)

    event_type: ClassVar[str] = "position"


@dataclass(slots=True)
class RunArtifactEvent(RunEvent):
    path: str = ""
    name: str = ""
    artifact_type: str = "file"
    size_bytes: int | None = None

    event_type: ClassVar[str] = "artifact"

    @classmethod
    def from_path(cls, run_id: str, path: str | Path, artifact_type: str = "file") -> "RunArtifactEvent":
        artifact_path = Path(path)
        try:
            size = artifact_path.stat().st_size
        except OSError:
            size = None
        return cls(
            run_id=run_id,
            path=str(artifact_path),
            name=artifact_path.name,
            artifact_type=artifact_type,
            size_bytes=size,
        )


@dataclass(slots=True)
class RunAgentTraceEvent(RunEvent):
    path: str = ""
    name: str = ""
    summary: str = ""

    event_type: ClassVar[str] = "agent_trace"


@dataclass(slots=True)
class RunFinishedEvent(RunEvent):
    returncode: int = 0
    duration_seconds: float | None = None

    event_type: ClassVar[str] = "finished"


@dataclass(slots=True)
class RunFailedEvent(RunEvent):
    returncode: int | None = None
    message: str = ""
    duration_seconds: float | None = None

    event_type: ClassVar[str] = "failed"


_EVENT_TYPES: dict[str, type[RunEvent]] = {
    cls.event_type: cls
    for cls in (
        RunStartedEvent,
        RunProgressEvent,
        RunLogEvent,
        RunOrderEvent,
        RunPositionEvent,
        RunArtifactEvent,
        RunAgentTraceEvent,
        RunFinishedEvent,
        RunFailedEvent,
    )
}


def event_from_dict(payload: dict[str, Any]) -> RunEvent:
    event_type = str(payload.get("type") or "event")
    cls = _EVENT_TYPES.get(event_type, RunEvent)
    allowed_fields = {item.name for item in fields(cls)}
    values = {key: value for key, value in payload.items() if key in allowed_fields}
    return cls(**values)
