from __future__ import annotations

import json
from pathlib import Path

from lumibot.cli import build_parser, main
from lumibot.cli.config import parse_param_assignments, read_lumibot_config


def test_cli_parser_includes_local_tools():
    parser = build_parser()
    assert parser.parse_args(["init", "demo"]).command == "init"
    assert parser.parse_args(["doctor", "--json"]).command == "doctor"
    assert parser.parse_args(["run", "--json"]).command == "run"
    assert parser.parse_args(["studio", "--no-open"]).command == "studio"


def test_param_assignments_parse_jsonish_values():
    assert parse_param_assignments(["fast=20", "enabled=true", 'symbols=["SPY","TLT"]', "name=demo"]) == {
        "fast": 20,
        "enabled": True,
        "symbols": ["SPY", "TLT"],
        "name": "demo",
    }


def test_init_creates_csv_project(tmp_path):
    project = tmp_path / "csv_project"
    code = main(
        [
            "init",
            str(project),
            "--data-source",
            "csv",
            "--symbol",
            "STUD",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-10",
        ]
    )
    assert code == 0
    assert (project / "lumibot.toml").exists()
    assert (project / "README.md").exists()
    assert (project / "strategies" / "strategy.py").exists()
    assert (project / "data" / "sample.csv").exists()
    config = read_lumibot_config(project / "lumibot.toml")
    assert config["strategy"]["class_name"] == "StudioCsvSingleSymbol"
    assert config["data_source"]["type"] == "pandas_csv"
    assert config["data_source"]["symbol"] == "STUD"


def test_doctor_json_passes_for_csv_project(tmp_path, capsys):
    project = _init_csv_project(tmp_path)
    capsys.readouterr()
    code = main(["doctor", "--config", str(project / "lumibot.toml"), "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert {check["status"] for check in payload["checks"]} <= {"pass", "warn"}


def test_run_csv_project_without_network(tmp_path, capsys):
    project = _init_csv_project(tmp_path)
    capsys.readouterr()
    code = main(["run", "--config", str(project / "lumibot.toml"), "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["status"]["state"] == "completed"
    run_dir = Path(payload["run_dir"])
    assert (run_dir / "run.json").exists()
    assert (run_dir / "status.json").exists()
    artifact_names = {artifact["name"] for artifact in payload["status"]["artifacts"]}
    assert "stats.csv" in artifact_names
    assert "trades.csv" in artifact_names


def _init_csv_project(tmp_path: Path) -> Path:
    project = tmp_path / "csv_project"
    code = main(
        [
            "init",
            str(project),
            "--data-source",
            "csv",
            "--symbol",
            "STUD",
            "--benchmark",
            "STUD",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-10",
        ]
    )
    assert code == 0
    return project
