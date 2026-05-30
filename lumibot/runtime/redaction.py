"""Redaction helpers shared by CLI, runtime events, and TUI views."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_KEY_FRAGMENTS = ("key", "token", "secret", "password", "auth")
REDACTED = "<redacted>"


def is_sensitive_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_value(key: str, value: Any) -> Any:
    if is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_mapping(item) if isinstance(item, Mapping) else item for item in value]
    return value


def redact_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {str(key): redact_value(str(key), value) for key, value in values.items()}
