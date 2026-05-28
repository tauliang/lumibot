"""Shared config helpers for local Lumibot CLI tools."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lumibot.studio.templates import get_template

CONFIG_FILENAME = "lumibot.toml"
DATA_SOURCE_ALIASES = {
    "csv": "pandas_csv",
    "pandas/csv": "pandas_csv",
    "pandas_csv": "pandas_csv",
    "yahoo": "yahoo",
}


def read_lumibot_config(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import tomllib

        with path.open("rb") as handle:
            return tomllib.load(handle)
    except ModuleNotFoundError:
        return _read_basic_toml(path)


def write_lumibot_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lumibot local backtest project",
        "# Run with: lumibot doctor && lumibot run",
        "",
    ]
    for section in ["project", "strategy", "data_source", "backtest", "parameters", "outputs"]:
        values = config.get(section) or {}
        if not values:
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if value is None:
                continue
            lines.append(f"{key} = {_format_toml_value(value)}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def resolve_config_path(config_value: str | None) -> Path:
    path = Path(os.path.expanduser(config_value or CONFIG_FILENAME))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_workspace(args: Any, config_path: Path | None = None) -> Path:
    workspace_value = getattr(args, "workspace", None)
    if workspace_value:
        return Path(os.path.expanduser(str(workspace_value))).resolve()
    config_path = config_path or resolve_config_path(getattr(args, "config", CONFIG_FILENAME))
    if config_path.exists() or getattr(args, "config", None):
        return config_path.parent.resolve()
    return Path.cwd().resolve()


def resolve_runs_dir(args: Any, workspace: Path, config: dict | None = None) -> Path:
    runs_dir = getattr(args, "runs_dir", None)
    if runs_dir:
        path = Path(os.path.expanduser(str(runs_dir)))
    else:
        project = (config or {}).get("project") or {}
        path = Path(os.path.expanduser(str(project.get("runs_dir") or "runs")))
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()


def build_run_payload(args: Any, workspace: Path, config: dict | None = None) -> dict:
    config = dict(config or {})
    strategy = dict(config.get("strategy") or {})
    data_source = dict(config.get("data_source") or {})
    backtest = dict(config.get("backtest") or {})
    parameters = dict(config.get("parameters") or {})
    outputs = dict(config.get("outputs") or {})

    if getattr(args, "template", None):
        strategy["source"] = "template"
        strategy["template_id"] = args.template
        strategy.pop("path", None)
        strategy.pop("class_name", None)
    if getattr(args, "strategy_path", None):
        strategy["source"] = "file"
        strategy["path"] = args.strategy_path
    if getattr(args, "class_name", None):
        strategy["class_name"] = args.class_name

    if "source" not in strategy:
        strategy["source"] = "file" if strategy.get("path") else "template"
    if strategy["source"] == "template":
        strategy.setdefault("template_id", "buy_and_hold")

    template_id = strategy.get("template_id")
    if template_id:
        try:
            template = get_template(str(template_id))
            parameters = {**template.default_parameters, **parameters}
            if strategy.get("source") == "template":
                strategy.setdefault("class_name", template.class_name)
        except Exception:
            pass

    data_type = getattr(args, "data_source", None) or data_source.get("type")
    if getattr(args, "csv_path", None):
        data_type = "pandas_csv"
        data_source["csv_path"] = args.csv_path
    if data_type:
        data_source["type"] = normalize_data_source_type(data_type)
    data_source.setdefault("type", "yahoo")
    _override(data_source, "symbol", getattr(args, "symbol", None))
    _override(data_source, "datetime_column", getattr(args, "datetime_column", None))
    _override(data_source, "timezone", getattr(args, "timezone", None))

    _override(backtest, "start", getattr(args, "start", None))
    _override(backtest, "end", getattr(args, "end", None))
    _override(backtest, "budget", getattr(args, "budget", None))
    _override(backtest, "benchmark_asset", getattr(args, "benchmark_asset", None))
    _override(backtest, "risk_free_rate", getattr(args, "risk_free_rate", None))
    _normalize_backtest_dates(backtest)

    for key in ["show_plot", "show_indicators", "save_tearsheet", "save_logfile"]:
        value = getattr(args, key, None)
        if value is not None:
            outputs[key] = value

    parameters.update(parse_param_assignments(getattr(args, "param", []) or []))

    return {
        "workspace": str(workspace),
        "strategy": strategy,
        "data_source": data_source,
        "backtest": backtest,
        "parameters": parameters,
        "outputs": outputs,
    }


def normalize_data_source_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return DATA_SOURCE_ALIASES.get(normalized, normalized)


def parse_param_assignments(assignments: list[str]) -> dict:
    parsed = {}
    for item in assignments:
        if "=" not in item:
            raise ValueError(f"Parameter override must use KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Parameter override has an empty key: {item}")
        parsed[key] = _parse_scalar(value.strip())
    return parsed


def config_for_init(
    project_name: str,
    template_id: str,
    symbol: str,
    benchmark: str,
    data_source_type: str,
    csv_path: str,
    budget: str,
    start: str,
    end: str,
) -> dict:
    template = get_template(template_id)
    data_source = {
        "type": data_source_type,
        "symbol": symbol,
        "datetime_column": "datetime",
        "timezone": "America/New_York",
    }
    if data_source_type == "pandas_csv":
        data_source["csv_path"] = csv_path
    parameters = {**template.default_parameters, "symbol": symbol}
    return {
        "project": {"name": project_name, "runs_dir": "runs"},
        "strategy": {
            "source": "file",
            "path": "strategies/strategy.py",
            "class_name": template.class_name,
            "template_id": template_id,
        },
        "data_source": data_source,
        "backtest": {
            "start": start,
            "end": end,
            "budget": float(str(budget).replace(",", "").replace("_", "")),
            "benchmark_asset": benchmark,
        },
        "parameters": parameters,
        "outputs": {
            "show_plot": False,
            "show_indicators": False,
            "save_tearsheet": False,
            "save_logfile": False,
        },
    }


def _override(target: dict, key: str, value: Any) -> None:
    if value not in (None, ""):
        target[key] = value


def _normalize_backtest_dates(backtest: dict) -> None:
    for key in ["start", "end"]:
        value = backtest.get(key)
        if isinstance(value, (date, datetime)):
            backtest[key] = value.isoformat()


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    return json.dumps(str(value))


def _read_basic_toml(path: Path) -> dict:
    result: dict[str, dict] = {}
    section: dict | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = result.setdefault(name, {})
            continue
        if section is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        section[key.strip()] = _parse_scalar(value.strip().split(" #", 1)[0])
    return result
