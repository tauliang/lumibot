from __future__ import annotations

import sys

from lumibot.runtime import BacktestRunConfig, RunController, RunFailedEvent, RunProgressEvent, event_from_dict
from lumibot.runtime.redaction import redact_mapping


def test_run_event_roundtrip_and_redaction():
    event = RunProgressEvent(
        run_id="abc",
        percent=12.5,
        portfolio_value="100,000.00",
        download_status={"api_key": "secret", "asset": "SPY"},
    )

    payload = event.to_dict()
    restored = event_from_dict(payload)

    assert payload["type"] == "progress"
    assert payload["download_status"]["api_key"] == "<redacted>"
    assert restored.run_id == "abc"
    assert restored.type == "progress"
    assert redact_mapping({"DATADOWNLOADER_API_KEY": "secret", "safe": "ok"}) == {
        "DATADOWNLOADER_API_KEY": "<redacted>",
        "safe": "ok",
    }


def test_run_controller_streams_logs_progress_and_artifacts(tmp_path):
    script = tmp_path / "strategy_script.py"
    script.write_text(
        "\n".join(
            [
                "import csv",
                "import json",
                "from pathlib import Path",
                "logdir = Path('logs')",
                "logdir.mkdir(exist_ok=True)",
                "with (logdir / 'progress.csv').open('w', newline='') as handle:",
                "    writer = csv.writer(handle)",
                "    writer.writerow(['timestamp','percent','elapsed','eta','portfolio_value','simulation_date','cash','total_return_pct','positions_json','orders_json','download_status'])",
                "    writer.writerow(['now','25.00','0:00:01','0:00:03','100.00','2025-01-02 09:30:00','90.00','0.00',json.dumps([{'asset': {'symbol': 'SPY'}, 'qty': 1}]),json.dumps([{'side': 'buy', 'qty': 1}]),'{}'])",
                "(logdir / 'sample_agent_detail.parquet').write_text('agent')",
                "print('hello from child')",
            ]
        ),
        encoding="utf-8",
    )

    config = BacktestRunConfig(script=script, cwd=tmp_path, python=sys.executable)
    handle = RunController().start(config)
    events = list(handle.events())

    assert any(event.type == "started" for event in events)
    assert any(event.type == "log" and "hello from child" in event.line for event in events)
    assert any(event.type == "progress" and event.percent == 25.0 for event in events)
    assert any(event.type == "position" for event in events)
    assert any(event.type == "order" for event in events)
    assert any(event.type == "artifact" and event.artifact_type == "agent_trace" for event in events)
    assert events[-1].type == "finished"


def test_run_controller_reports_failures(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("raise SystemExit(7)\n", encoding="utf-8")

    handle = RunController().start(BacktestRunConfig(script=script, cwd=tmp_path, python=sys.executable))
    events = list(handle.events())

    failed = [event for event in events if isinstance(event, RunFailedEvent)]
    assert failed
    assert failed[-1].returncode == 7
