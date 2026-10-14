"""`fixture_site` fixtures: start a site, stop it afterwards (design D9 of 000-scaffold-project)."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest

from tests.fixture_site.hosts import FixtureHosts, StartHosts, hosts_for
from tests.fixture_site.routes import Site
from tests.fixture_site.server import RunningServer, ServerHandle

StartSite = Callable[[Site], ServerHandle]


def _serve_sites() -> Iterator[StartSite]:
    with ExitStack() as running:

        def start(site: Site) -> ServerHandle:
            server = RunningServer(site)
            running.callback(server.stop)
            return server.handle

        yield start


@pytest.fixture
def fixture_site() -> Iterator[StartSite]:
    yield from _serve_sites()


@pytest.fixture(scope="module")
def module_fixture_site() -> Iterator[StartSite]:
    yield from _serve_sites()


@pytest.fixture
def fixture_hosts(fixture_site: StartSite) -> StartHosts:
    """Two instances, the second for other.test, behind the DNS resolver hook."""

    def start(site: Site, other: Site) -> FixtureHosts:
        return hosts_for(fixture_site(site), fixture_site(other))

    return start
