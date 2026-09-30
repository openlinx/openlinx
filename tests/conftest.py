"""Test loop, network guard, home isolation (designs D5, D8, D13, D15 of 000-scaffold-project)."""

import asyncio
import os
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from hypothesis import settings

from spider.aio import loop_factory
from tests.support.network import block_remote_connections

pytest_plugins = ["tests.support.workspace"]

settings.register_profile("dev")
settings.register_profile("ci", deadline=None, print_blob=True, max_examples=200)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    return {"loop_factory": loop_factory}


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    block_remote_connections(monkeypatch)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
