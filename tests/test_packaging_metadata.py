from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_cli_and_tui_extra():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["lumibot"] == "lumibot.cli:main"
    assert "textual>=8,<9" in pyproject["project"]["optional-dependencies"]["tui"]
    assert "rich>=15,<16" in pyproject["project"]["optional-dependencies"]["tui"]
    assert "License :: OSI Approved :: MIT License" not in pyproject["project"]["classifiers"]


def test_setup_py_is_metadata_shim():
    setup_text = (ROOT / "setup.py").read_text(encoding="utf-8")

    assert "Project metadata lives in pyproject.toml" in setup_text
    assert "version=" not in setup_text
    assert "BuildWithThetaJar" in setup_text
