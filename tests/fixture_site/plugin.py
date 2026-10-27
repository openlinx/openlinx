"""`fixture_site` fixtures: start a site, stop it afterwards (design D9 of 000-scaffold-project)."""

import ssl
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
    on_http_port,
)
from tests.fixture_site.routes import Site
from tests.fixture_site.server import RunningServer, Serve, ServerHandle
from tests.fixture_site.tls import SiteOrBuilder, StartTlsHosts, TlsHosts, tls_hosts_for
from tests.support.proxy import ForwardProxy, StartProxy

StartSite = Callable[[Site], ServerHandle]


def _serve_sites() -> Iterator[Serve]:
    with ExitStack() as running:

        def start(site: Site, tls: ssl.SSLContext | None = None) -> ServerHandle:
            server = RunningServer(site, tls=tls)
            running.callback(server.stop)
            return server.handle

        yield start


@pytest.fixture
def fixture_site() -> Iterator[Serve]:
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
        return NamedHosts(servers, FixtureResolver(on_http_port(servers)))

    return start


@pytest.fixture
def fixture_tls_hosts(fixture_site: Serve) -> StartTlsHosts:
    """site.test over http and https, and two https listeners whose certificates fail,
    behind the DNS resolver hook."""

    def start(site: SiteOrBuilder, other: Site) -> TlsHosts:
        return tls_hosts_for(fixture_site, site, other)

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
