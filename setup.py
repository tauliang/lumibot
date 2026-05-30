"""Compatibility shim for setuptools builds.

Project metadata lives in pyproject.toml. This file remains for one release cycle
so the custom ThetaTerminal.jar build hook can stay wired into setuptools.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
if DIST_DIR.exists():
    shutil.rmtree(DIST_DIR)


class BuildWithThetaJar(_build_py):
    """Optionally bundle ThetaTerminal.jar if present locally."""

    def run(self):
        super().run()
        self._maybe_copy_theta_terminal()

    def _maybe_copy_theta_terminal(self):
        src = PROJECT_ROOT / "lumibot" / "resources" / "ThetaTerminal.jar"
        if not src.exists():
            print("[build] ThetaTerminal.jar not found, skipping bundling (ThetaData is optional).")
            return
        dest = Path(self.build_lib) / "lumibot" / "resources" / "ThetaTerminal.jar"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"[build] Bundled ThetaTerminal.jar -> {dest} (size={dest.stat().st_size} bytes)")


setup(cmdclass={"build_py": BuildWithThetaJar})
