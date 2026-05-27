"""Artifact, log, and metrics helpers for the Local Backtest Studio."""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SECRET_VALUE_RE = re.compile(
    r"(?i)(API_KEY|SECRET|TOKEN|PASSWORD)([\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)"
)


def redact_text(text: str) -> str:
    """Redact common secret-looking values from Studio logs and API responses."""

    return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    tmp.replace(path)


def safe_artifact_name(name: str) -> str:
    normalized = str(name or "").strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("artifact name is required")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError("invalid artifact name")
    return normalized


def artifact_dir(run_dir: Path) -> Path:
    return run_dir / "artifacts"


def list_artifacts(run_dir: Path) -> list[dict]:
    root = artifact_dir(run_dir)
    if not root.exists():
        return []
    artifacts = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        artifacts.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "kind": _artifact_kind(path.name),
            }
        )
    return artifacts


def _artifact_kind(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".html"):
        return "html"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".parquet"):
        return "parquet"
    return "file"


def resolve_artifact_path(run_dir: Path, artifact_name: str) -> Path:
    name = safe_artifact_name(artifact_name)
    path = (artifact_dir(run_dir) / name).resolve()
    root = artifact_dir(run_dir).resolve()
    if root not in path.parents and path != root:
        raise ValueError("artifact path escaped run directory")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(name)
    return path


def read_progress(run_dir: Path) -> dict:
    progress_path = run_dir / "logs" / "progress.csv"
    if not progress_path.exists():
        return {}
    try:
        with progress_path.open("r", encoding="utf-8", errors="replace") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return {}
    if not rows:
        return {}
    row = rows[-1]
    return {
        "progress_pct": _to_float(row.get("percent")),
        "current_datetime": row.get("simulation_date") or None,
        "portfolio_value": _to_float(row.get("portfolio_value")),
        "cash": _to_float(row.get("cash")),
        "total_return_pct": _to_float(row.get("total_return_pct")),
        "elapsed": row.get("elapsed") or None,
        "eta": row.get("eta") or None,
    }


def extract_metrics(run_dir: Path, runtime_seconds: float | None = None) -> dict:
    metrics: dict[str, Any] = {
        "total_return": None,
        "cagr": None,
        "sharpe": None,
        "sortino": None,
        "volatility": None,
        "max_drawdown": None,
        "win_rate": None,
        "number_of_trades": None,
        "final_portfolio_value": None,
        "runtime_seconds": runtime_seconds,
    }
    metrics.update(_metrics_from_tearsheet_json(artifact_dir(run_dir) / "tearsheet_metrics.json"))
    stats_metrics = _metrics_from_stats_csv(artifact_dir(run_dir) / "stats.csv")
    for key, value in stats_metrics.items():
        if value is not None:
            metrics[key] = value
    trades_metrics = _metrics_from_trades_csv(artifact_dir(run_dir) / "trades.csv")
    for key, value in trades_metrics.items():
        if value is not None:
            metrics[key] = value
    return metrics


def read_table(run_dir: Path, artifact_name: str, offset: int = 0, limit: int = 100) -> dict:
    path = resolve_artifact_path(run_dir, artifact_name)
    if path.suffix.lower() != ".csv":
        raise ValueError("table preview only supports CSV artifacts")
    offset = max(0, int(offset or 0))
    limit = max(1, min(500, int(limit or 100)))
    rows = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        for total, row in enumerate(reader, start=1):
            if total <= offset:
                continue
            if len(rows) >= limit:
                continue
            rows.append({key: redact_text(str(value)) for key, value in row.items()})
    return {"columns": columns, "rows": rows, "offset": offset, "limit": limit, "total": total}


def chart_data(run_dir: Path) -> dict:
    stats_path = artifact_dir(run_dir) / "stats.csv"
    if not stats_path.exists():
        return {"equity": [], "drawdown": []}
    try:
        with stats_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except Exception:
        return {"equity": [], "drawdown": []}
    if not rows:
        return {"equity": [], "drawdown": []}
    columns = rows[0].keys()
    dt_col = _first_existing(columns, ["datetime", "timestamp", "time", "date"])
    pv_col = _first_existing(columns, ["portfolio_value", "Portfolio Value", "strategy", "Strategy"])
    cash_col = _first_existing(columns, ["cash", "Cash"])
    benchmark_col = _first_existing(columns, ["benchmark", "Benchmark", "SPY"])
    equity = []
    values = []
    for index, row in enumerate(rows):
        value = _to_float(row.get(pv_col)) if pv_col else None
        if value is None:
            continue
        values.append(value)
        equity.append(
            {
                "x": row.get(dt_col) if dt_col else index,
                "portfolio_value": value,
                "cash": _to_float(row.get(cash_col)) if cash_col else None,
                "benchmark": _to_float(row.get(benchmark_col)) if benchmark_col else None,
            }
        )
    peak = None
    drawdown = []
    for point in equity:
        value = point["portfolio_value"]
        peak = value if peak is None else max(peak, value)
        dd = 0.0 if not peak else (value / peak) - 1.0
        drawdown.append({"x": point["x"], "drawdown": dd})
    return {"equity": equity, "drawdown": drawdown}


def _metrics_from_tearsheet_json(path: Path) -> dict:
    payload = read_json(path, {})
    scalar = payload.get("scalar_metrics") if isinstance(payload, dict) else {}
    if not isinstance(scalar, dict):
        scalar = {}
    return {
        "total_return": _metric_value(scalar, ["Total Return", "Cumulative Return", "Return"]),
        "cagr": _metric_value(scalar, ["CAGR", "CAGR%", "CAGR Pct"]),
        "sharpe": _metric_value(scalar, ["Sharpe", "Sharpe Ratio"]),
        "sortino": _metric_value(scalar, ["Sortino", "Sortino Ratio"]),
        "volatility": _metric_value(scalar, ["Volatility", "Annualized Volatility"]),
        "max_drawdown": _metric_value(scalar, ["Max Drawdown", "Maximum Drawdown"]),
        "win_rate": _metric_value(scalar, ["Win Rate", "Win Days", "Win Rate Pct"]),
    }


def _metrics_from_stats_csv(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return {}
    if not rows:
        return {}
    columns = rows[-1].keys()
    pv_col = _first_existing(columns, ["portfolio_value", "Portfolio Value", "strategy", "Strategy"])
    if pv_col is None:
        return {}
    values = [_to_float(row.get(pv_col)) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    if not values:
        return {}
    final_value = values[-1]
    initial_value = values[0]
    total_return = (final_value / initial_value) - 1.0 if initial_value else None
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            max_drawdown = min(max_drawdown, (value / peak) - 1.0)
    return {
        "final_portfolio_value": final_value,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
    }


def _metrics_from_trades_csv(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return {}
    if not rows:
        return {"number_of_trades": 0}
    status_col = _first_existing(rows[0].keys(), ["status", "Status"])
    pnl_col = _first_existing(rows[0].keys(), ["realized_pnl", "pnl", "profit_loss"])
    fills = rows
    if status_col:
        fills = [row for row in rows if str(row.get(status_col, "")).lower() in {"fill", "filled"}]
    win_rate = None
    if pnl_col:
        pnls = [_to_float(row.get(pnl_col)) for row in fills]
        pnls = [pnl for pnl in pnls if pnl is not None]
        if pnls:
            win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls)
    return {"number_of_trades": len(fills), "win_rate": win_rate}


def _metric_value(metrics: dict, names: list[str]) -> float | str | None:
    lower_lookup = {str(key).lower(): value for key, value in metrics.items()}
    for name in names:
        if name.lower() in lower_lookup:
            return _coerce_metric(lower_lookup[name.lower()])
    return None


def _coerce_metric(value: Any) -> float | str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    percent = text.endswith("%")
    cleaned = text.replace("%", "").replace(",", "")
    try:
        parsed = float(cleaned)
    except ValueError:
        return text
    if not math.isfinite(parsed):
        return None
    return parsed / 100.0 if percent else parsed


def _to_float(value: Any) -> float | None:
    coerced = _coerce_metric(value)
    return coerced if isinstance(coerced, float) else None


def _first_existing(columns, candidates: list[str]) -> str | None:
    columns_list = list(columns or [])
    exact = {column: column for column in columns_list}
    lowered = {str(column).lower(): column for column in columns_list}
    for candidate in candidates:
        if candidate in exact:
            return exact[candidate]
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None
