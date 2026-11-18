"""Create isolated temporary Workspaces for tests."""

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class TempWorkspace:
    home: Path
    root: Path


@pytest.fixture
def temp_workspace(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> TempWorkspace:
    # Under the fake home on purpose: Workspace discovery stops at the home folder.
    root = isolated_home / "work"
    root.mkdir()
    monkeypatch.chdir(root)
    return TempWorkspace(home=isolated_home, root=root)
