"""Run specification, discovery, and preflight helpers for the Studio."""

from __future__ import annotations

import ast
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .templates import get_template

SCHEMA_VERSION = 1
SUPPORTED_DATA_SOURCES = {"yahoo", "pandas_csv"}


class StudioValidationError(ValueError):
    """Raised when a Studio run request cannot be normalized into a RunSpec."""


def new_run_id() -> str:
    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def normalize_run_spec(payload: dict, workspace: Path, run_dir: Path, run_id: str | None = None) -> dict:
    run_id = run_id or str(payload.get("run_id") or new_run_id())
    workspace = workspace.resolve()
    run_dir = run_dir.resolve()

    strategy_payload = payload.get("strategy") or {}
    data_payload = payload.get("data_source") or {}
    backtest_payload = payload.get("backtest") or {}
    outputs_payload = payload.get("outputs") or {}

    source = str(strategy_payload.get("source") or "template").strip().lower()
    template_id = strategy_payload.get("template_id") or "buy_and_hold"
    class_name = strategy_payload.get("class_name") or ""
    strategy_path = strategy_payload.get("path") or ""

    if source not in {"template", "file"}:
        raise StudioValidationError("strategy.source must be 'template' or 'file'")

    if source == "template":
        template = get_template(str(template_id))
        class_name = class_name or template.class_name
        strategy_path = str(run_dir / "strategy.py")
    else:
        if not strategy_path:
            raise StudioValidationError("strategy.path is required for file strategies")
        strategy_path = str(resolve_user_path(strategy_path, workspace))
        if not class_name:
            discovered = discover_strategy_classes(Path(strategy_path))
            if len(discovered) == 1:
                class_name = discovered[0]["class_name"]
            elif not discovered:
                raise StudioValidationError("No Strategy subclass was found in strategy.path")
            else:
                raise StudioValidationError("strategy.class_name is required when multiple strategy classes exist")

    data_type = str(data_payload.get("type") or "yahoo").strip().lower()
    if data_type not in SUPPORTED_DATA_SOURCES:
        raise StudioValidationError("data_source.type must be 'yahoo' or 'pandas_csv'")

    symbol = str(data_payload.get("symbol") or _template_default_symbol(template_id) or "SPY").strip().upper()
    csv_path = data_payload.get("csv_path") or ""
    if data_type == "pandas_csv":
        if not csv_path:
            raise StudioValidationError("data_source.csv_path is required for Pandas/CSV runs")
        csv_path = str(resolve_user_path(csv_path, workspace))

    parameters = payload.get("parameters") or {}
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters) if parameters.strip() else {}
        except json.JSONDecodeError as exc:
            raise StudioValidationError(f"parameters must be a JSON object: {exc}") from exc
    if not isinstance(parameters, dict):
        raise StudioValidationError("parameters must be a JSON object")
    if "symbol" not in parameters and symbol:
        parameters = {**parameters, "symbol": symbol}

    start = _required_date(backtest_payload.get("start"), "backtest.start")
    end = _required_date(backtest_payload.get("end"), "backtest.end")
    budget = _positive_float(backtest_payload.get("budget", 100000), "backtest.budget")
    risk_free_rate = _optional_float(backtest_payload.get("risk_free_rate"), "backtest.risk_free_rate")
    benchmark_asset = str(backtest_payload.get("benchmark_asset") or "SPY").strip().upper()

    spec = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "workspace": str(workspace),
        "strategy": {
            "source": source,
            "path": strategy_path,
            "class_name": class_name,
            "template_id": template_id if source == "template" else None,
        },
        "data_source": {
            "type": data_type,
            "symbol": symbol,
            "csv_path": csv_path,
            "datetime_column": str(data_payload.get("datetime_column") or "datetime"),
            "timezone": str(data_payload.get("timezone") or "America/New_York"),
        },
        "backtest": {
            "start": start,
            "end": end,
            "budget": budget,
            "benchmark_asset": benchmark_asset,
            "risk_free_rate": risk_free_rate,
        },
        "parameters": parameters,
        "outputs": {
            "show_plot": _bool(outputs_payload.get("show_plot"), True),
            "show_indicators": _bool(outputs_payload.get("show_indicators"), True),
            "save_tearsheet": _bool(outputs_payload.get("save_tearsheet"), True),
            "save_logfile": _bool(outputs_payload.get("save_logfile"), False),
        },
    }
    validate_run_spec(spec)
    return spec


def validate_run_spec(spec: dict) -> None:
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise StudioValidationError(f"Unsupported RunSpec schema_version: {spec.get('schema_version')}")
    if not spec.get("run_id"):
        raise StudioValidationError("run_id is required")
    if spec.get("data_source", {}).get("type") not in SUPPORTED_DATA_SOURCES:
        raise StudioValidationError("Unsupported data source")
    start = datetime.fromisoformat(spec["backtest"]["start"])
    end = datetime.fromisoformat(spec["backtest"]["end"])
    if end <= start:
        raise StudioValidationError("backtest.end must be after backtest.start")
    if float(spec["backtest"]["budget"]) <= 0:
        raise StudioValidationError("backtest.budget must be positive")
    strategy = spec.get("strategy") or {}
    if not strategy.get("class_name"):
        raise StudioValidationError("strategy.class_name is required")
    if not strategy.get("path"):
        raise StudioValidationError("strategy.path is required")


def build_initial_status(run_id: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "state": "queued",
        "progress_pct": 0.0,
        "phase": "queued",
        "current_datetime": None,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error_summary": None,
        "metrics_summary": {},
        "artifacts": [],
    }


def build_preflight(spec: dict, runs_dir: Path) -> list[dict]:
    checks = []
    checks.append(_check("pass" if sys.version_info >= (3, 10) else "fail", "Python 3.10+", sys.version.split()[0]))
    try:
        import lumibot

        checks.append(_check("pass", "Lumibot import", getattr(lumibot, "__version__", "unknown")))
    except Exception as exc:
        checks.append(_check("fail", "Lumibot import", str(exc)))

    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks.append(_check("pass", "Runs directory writable", str(runs_dir)))
    except Exception as exc:
        checks.append(_check("fail", "Runs directory writable", str(exc)))

    data_source = spec.get("data_source", {})
    if data_source.get("type") == "yahoo":
        checks.append(_check("warn", "Yahoo data", "Yahoo is daily stock/ETF data only."))
    if data_source.get("type") == "pandas_csv":
        csv_path = Path(data_source.get("csv_path") or "")
        checks.append(_check("pass" if csv_path.exists() else "fail", "CSV file", str(csv_path)))

    benchmark = str(spec.get("backtest", {}).get("benchmark_asset") or "").strip()
    checks.append(_check("pass" if benchmark else "warn", "Benchmark", benchmark or "No benchmark set."))

    end_date = datetime.fromisoformat(spec["backtest"]["end"]).date()
    if end_date > date.today():
        checks.append(_check("warn", "Future end date", f"{end_date.isoformat()} is after today."))

    strategy_path = Path(spec.get("strategy", {}).get("path") or "")
    classes = discover_strategy_classes(strategy_path)
    class_names = {item["class_name"] for item in classes}
    class_name = spec.get("strategy", {}).get("class_name")
    if strategy_path.exists() and class_name in class_names:
        checks.append(_check("pass", "Strategy class", class_name))
    elif strategy_path.exists():
        checks.append(_check("fail", "Strategy class", f"{class_name} not found."))
    else:
        checks.append(_check("fail", "Strategy file", str(strategy_path)))

    for warning in static_strategy_warnings(strategy_path):
        checks.append(_check("warn", warning["title"], warning["detail"]))
    return checks


def discover_strategy_classes(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    classes = []
    fallback = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
        entry = {"class_name": node.name, "line": node.lineno}
        bases = {_base_name(base) for base in node.bases}
        if "Strategy" in bases or "_Strategy" in bases:
            classes.append(entry)
        elif "on_trading_iteration" in methods:
            fallback.append(entry)
    return classes or fallback


def static_strategy_warnings(path: Path) -> list[dict]:
    if not path.exists() or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    warnings = []
    if "datetime.now(" in text or ".now(" in text:
        warnings.append(
            {
                "title": "Possible wall-clock datetime",
                "detail": "Use self.get_datetime() inside backtests instead of datetime.now().",
            }
        )
    if "date.today(" in text:
        warnings.append(
            {
                "title": "Possible wall-clock date",
                "detail": "Use the simulated strategy datetime instead of date.today().",
            }
        )
    if "benchmark_asset" not in text:
        warnings.append(
            {
                "title": "Benchmark not set in strategy file",
                "detail": "Studio will use the benchmark configured in the run form.",
            }
        )
    return warnings


def materialize_template_strategy(spec: dict) -> None:
    strategy = spec["strategy"]
    if strategy.get("source") != "template":
        return
    template = get_template(strategy.get("template_id") or "buy_and_hold")
    path = Path(strategy["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.code, encoding="utf-8")


def resolve_user_path(path: str, workspace: Path) -> Path:
    candidate = Path(os.path.expanduser(str(path)))
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate.resolve()


def _template_default_symbol(template_id: str | None) -> str | None:
    if not template_id:
        return None
    try:
        return get_template(str(template_id)).default_symbol
    except Exception:
        return None


def _required_date(value: Any, field: str) -> str:
    if value in (None, ""):
        raise StudioValidationError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise StudioValidationError(f"{field} must be ISO date or datetime") from exc
    return parsed.date().isoformat() if "T" not in str(value) and " " not in str(value) else parsed.isoformat()


def _positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(str(value).replace("$", "").replace(",", "").replace("_", ""))
    except (TypeError, ValueError) as exc:
        raise StudioValidationError(f"{field} must be a positive number") from exc
    if parsed <= 0:
        raise StudioValidationError(f"{field} must be positive")
    return parsed


def _optional_float(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StudioValidationError(f"{field} must be a number") from exc


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _base_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _check(status: str, title: str, detail: str) -> dict:
    return {"status": status, "title": title, "detail": detail}
