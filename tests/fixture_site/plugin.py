"""The `fixture_site` fixture: start a site, stop it after the test (design D9 of 000)."""

from collections.abc import Callable, Iterator

import pytest

from tests.fixture_site.routes import Site
from tests.fixture_site.server import RunningServer, ServerHandle

StartSite = Callable[[Site], ServerHandle]


@pytest.fixture
def fixture_site() -> Iterator[StartSite]:
    servers: list[RunningServer] = []

    def start(site: Site) -> ServerHandle:
        server = RunningServer(site)
        servers.append(server)
        return server.handle

    yield start
    for server in servers:
        server.stop()
