"""Home, proxy and network isolation for every test, as a pytest plugin (design D13 of 000)."""

from pathlib import Path

import pytest

from tests.support.network import block_remote_connections

PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY")


@pytest.fixture(autouse=True)
def no_proxy_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


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
