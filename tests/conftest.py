"""Hypothesis profiles and home isolation (designs D5 and D8 of 000-scaffold-project)."""

import os
from pathlib import Path

import pytest
from hypothesis import settings

settings.register_profile("dev")
settings.register_profile("ci", deadline=None, print_blob=True, max_examples=200)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    # Path.home() reads HOME on POSIX and USERPROFILE on Windows.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
