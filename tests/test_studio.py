from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lumibot.cli import build_parser
from lumibot.studio.app import create_app
from lumibot.studio.artifacts import (
    extract_metrics,
    list_artifacts,
    read_progress,
    redact_text,
    resolve_artifact_path,
)
from lumibot.studio.models import discover_strategy_classes, normalize_run_spec, validate_run_spec
from lumibot.studio.templates import list_templates


def test_cli_studio_args_parse():
    parser = build_parser()
    args = parser.parse_args(["studio", "--host", "127.0.0.1", "--port", "0", "--workspace", "/tmp/x", "--no-open"])
    assert args.command == "studio"
    assert args.host == "127.0.0.1"
    assert args.port == 0
    assert args.workspace == "/tmp/x"
    assert args.open_browser is False


def test_templates_are_listed():
    templates = list_templates()
    ids = {template["template_id"] for template in templates}
    assert {"buy_and_hold", "moving_average_crossover", "portfolio_rebalance", "csv_single_symbol"} <= ids


def test_strategy_discovery_finds_strategy_subclasses(tmp_path):
    strategy_file = tmp_path / "strategy.py"
    strategy_file.write_text(
        """
from lumibot.strategies import Strategy


class MyStrategy(Strategy):
    def initialize(self):
        pass

    def on_trading_iteration(self):
        pass
""",
        encoding="utf-8",
    )
    classes = discover_strategy_classes(strategy_file)
    assert classes == [{"class_name": "MyStrategy", "line": 5}]


def test_run_spec_validation_for_csv_template(tmp_path):
    csv_path = _write_fixture_csv(tmp_path / "data.csv")
    spec = normalize_run_spec(
        {
            "strategy": {"source": "template", "template_id": "csv_single_symbol"},
            "data_source": {"type": "pandas_csv", "symbol": "STUD", "csv_path": str(csv_path)},
            "backtest": {"start": "2024-01-02", "end": "2024-01-10", "budget": 10000, "benchmark_asset": "STUD"},
            "parameters": {"symbol": "STUD"},
            "outputs": {"show_plot": False, "show_indicators": False, "save_tearsheet": False},
        },
        tmp_path,
        tmp_path / "runs" / "run_1",
        run_id="run_1",
    )
    validate_run_spec(spec)
    assert spec["schema_version"] == 1
    assert spec["strategy"]["path"].endswith("strategy.py")
    assert spec["data_source"]["type"] == "pandas_csv"


def test_artifact_index_metrics_progress_and_redaction(tmp_path):
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    logs = run_dir / "logs"
    artifacts.mkdir(parents=True)
    logs.mkdir()
    (artifacts / "tearsheet_metrics.json").write_text(
        json.dumps({"scalar_metrics": {"Sharpe": 1.23, "Total Return": "8.00%", "Max Drawdown": "-3.00%"}}),
        encoding="utf-8",
    )
    (artifacts / "stats.csv").write_text(
        "datetime,portfolio_value,cash\n2024-01-02,10000,1000\n2024-01-03,10800,900\n",
        encoding="utf-8",
    )
    (artifacts / "trades.csv").write_text("status,realized_pnl\nfill,12\nfill,-4\n", encoding="utf-8")
    (logs / "progress.csv").write_text(
        "timestamp,percent,elapsed,eta,portfolio_value,simulation_date,cash,total_return_pct,positions_json\n"
        "now,50,1,1,10500,2024-01-03,900,5,[]\n",
        encoding="utf-8",
    )

    assert {artifact["name"] for artifact in list_artifacts(run_dir)} == {
        "stats.csv",
        "tearsheet_metrics.json",
        "trades.csv",
    }
    metrics = extract_metrics(run_dir, runtime_seconds=2.5)
    assert metrics["sharpe"] == 1.23
    assert metrics["total_return"] == pytest.approx(0.08)
    assert metrics["final_portfolio_value"] == 10800
    assert metrics["number_of_trades"] == 2
    progress = read_progress(run_dir)
    assert progress["progress_pct"] == 50
    assert progress["current_datetime"] == "2024-01-03"
    assert "SECRET='[REDACTED]'" in redact_text("SECRET='abc123'")


def test_artifact_path_traversal_rejected(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "artifacts").mkdir(parents=True)
    with pytest.raises(ValueError):
        resolve_artifact_path(run_dir, "../run.json")


def test_studio_api_runs_csv_template_without_network(tmp_path):
    csv_path = _write_fixture_csv(tmp_path / "data.csv")
    app = create_app(workspace=tmp_path, runs_dir=tmp_path / "runs")
    client = app.test_client()

    response = client.post(
        "/api/runs",
        json={
            "strategy": {"source": "template", "template_id": "csv_single_symbol"},
            "data_source": {"type": "pandas_csv", "symbol": "STUD", "csv_path": str(csv_path)},
            "backtest": {"start": "2024-01-02", "end": "2024-01-10", "budget": 10000, "benchmark_asset": "STUD"},
            "parameters": {"symbol": "STUD"},
            "outputs": {"show_plot": False, "show_indicators": False, "save_tearsheet": False},
        },
    )
    assert response.status_code == 201, response.get_json()
    run_id = response.get_json()["run_id"]
    payload = _wait_for_terminal_run(client, run_id)
    assert payload["status"]["state"] == "completed", payload
    assert (tmp_path / "runs" / run_id / "run.json").exists()
    assert (tmp_path / "runs" / run_id / "status.json").exists()
    artifact_names = {artifact["name"] for artifact in payload["status"]["artifacts"]}
    assert "stats.csv" in artifact_names
    assert "trades.csv" in artifact_names

    artifacts_response = client.get(f"/api/runs/{run_id}/artifacts")
    assert artifacts_response.status_code == 200
    table_response = client.get(f"/api/runs/{run_id}/table/trades.csv?offset=0&limit=5")
    assert table_response.status_code == 200


def test_studio_api_reports_failing_strategy(tmp_path):
    csv_path = _write_fixture_csv(tmp_path / "data.csv")
    strategy_file = tmp_path / "bad_strategy.py"
    strategy_file.write_text(
        """
from lumibot.strategies import Strategy


class BadStrategy(Strategy):
    def initialize(self):
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        raise RuntimeError("intentional studio failure")
""",
        encoding="utf-8",
    )
    app = create_app(workspace=tmp_path, runs_dir=tmp_path / "runs")
    client = app.test_client()
    response = client.post(
        "/api/runs",
        json={
            "strategy": {"source": "file", "path": str(strategy_file), "class_name": "BadStrategy"},
            "data_source": {"type": "pandas_csv", "symbol": "STUD", "csv_path": str(csv_path)},
            "backtest": {"start": "2024-01-02", "end": "2024-01-10", "budget": 10000, "benchmark_asset": "STUD"},
            "parameters": {"symbol": "STUD"},
            "outputs": {"show_plot": False, "show_indicators": False, "save_tearsheet": False},
        },
    )
    assert response.status_code == 201, response.get_json()
    run_id = response.get_json()["run_id"]
    payload = _wait_for_terminal_run(client, run_id)
    assert payload["status"]["state"] == "failed"
    logs = client.get(f"/api/runs/{run_id}/logs").get_json()["text"]
    assert "intentional studio failure" in logs


def _wait_for_terminal_run(client, run_id: str, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    payload = {}
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        if payload["status"]["state"] in {"completed", "failed", "canceled"}:
            return payload
        time.sleep(0.5)
    raise AssertionError(f"Run did not finish: {payload}")


def _write_fixture_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "datetime,open,high,low,close,volume",
                "2024-01-02,100,101,99,100,1000",
                "2024-01-03,100,103,99,102,1000",
                "2024-01-04,102,104,101,103,1000",
                "2024-01-05,103,105,102,104,1000",
                "2024-01-08,104,106,103,105,1000",
                "2024-01-09,105,107,104,106,1000",
                "2024-01-10,106,108,105,107,1000",
            ]
        ),
        encoding="utf-8",
    )
    return path
