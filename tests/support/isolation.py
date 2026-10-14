"""Home, proxy and network isolation as a pytest plugin (design D13 of 000-scaffold-project)."""

from collections.abc import Iterator
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
def network_guard(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    blocked = block_remote_connections(monkeypatch)
    yield
    # The crawler records a refused request as a URL's error, so the block alone may stay unseen.
    if blocked and request.node.get_closest_marker("blocks_remote") is None:
        pytest.fail(f"the test tried to reach the network: {'; '.join(blocked)}")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
