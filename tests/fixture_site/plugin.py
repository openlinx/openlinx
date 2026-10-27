"""`fixture_site` fixtures: start a site, stop it afterwards (design D9 of 000-scaffold-project)."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack

import pytest
from aiohttp.abc import AbstractResolver

from tests.fixture_site.hosts import (
    FixtureHosts,
    FixtureResolver,
    NamedHosts,
    StartHosts,
    StartNamedHosts,
    hosts_for,
)
from tests.fixture_site.routes import Site
from tests.fixture_site.server import RunningServer, ServerHandle
from tests.support.proxy import ForwardProxy, StartProxy

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


@pytest.fixture
def fixture_named_hosts(fixture_site: StartSite) -> StartNamedHosts:
    """An instance per host name, behind the DNS resolver hook."""

    def start(sites: Mapping[str, Site]) -> NamedHosts:
        servers = {name: fixture_site(site) for name, site in sites.items()}
        return NamedHosts(servers, FixtureResolver(servers))

    return start


@pytest.fixture
def fixture_proxy() -> Iterator[StartProxy]:
    """A forward proxy that resolves names with the DNS resolver hook it is given."""
    with ExitStack() as running:

        def start(resolver: AbstractResolver) -> ForwardProxy:
            proxy = ForwardProxy(resolver)
            running.callback(proxy.stop)
            return proxy

        yield start
