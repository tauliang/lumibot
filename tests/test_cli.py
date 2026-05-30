from __future__ import annotations

from lumibot.cli import _parse_env, main


def test_parse_env_values():
    assert _parse_env(["A=1", "B=two=three"]) == {"A": "1", "B": "two=three"}


def test_tui_missing_optional_dependency_message(monkeypatch, capsys):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "lumibot.tui.app":
            raise ImportError("No module named 'textual'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    assert main(["tui"]) == 2
    captured = capsys.readouterr()
    assert 'pip install "lumibot[tui]"' in captured.err
    assert "textual" in captured.err
