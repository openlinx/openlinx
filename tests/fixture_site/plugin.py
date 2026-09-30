"""`fixture_site` fixtures: start a site, stop it afterwards (design D9 of 000-scaffold-project)."""

from collections.abc import Callable, Iterator

import pytest

from tests.fixture_site.routes import Site
from tests.fixture_site.server import RunningServer, ServerHandle

StartSite = Callable[[Site], ServerHandle]


def _serve_sites() -> Iterator[StartSite]:
    servers: list[RunningServer] = []

    def start(site: Site) -> ServerHandle:
        server = RunningServer(site)
        servers.append(server)
        return server.handle

    yield start
    for server in servers:
        server.stop()


@pytest.fixture
def fixture_site() -> Iterator[StartSite]:
    yield from _serve_sites()


@pytest.fixture(scope="module")
def module_fixture_site() -> Iterator[StartSite]:
    yield from _serve_sites()
