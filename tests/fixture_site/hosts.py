"""The DNS resolver hook: fixture host names for multi-host Crawls (020-add-crawl-core D15)."""

import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiohttp.abc import AbstractResolver, ResolveResult

from tests.fixture_site.routes import Site
from tests.fixture_site.server import ServerHandle

SITE_HOSTS = ("site.test", "www.site.test")
OTHER_HOST = "other.test"
HTTP_PORT = 80

# A name and the port a URL asks for on it.
type Listener = tuple[str, int]


class FixtureResolver(AbstractResolver):
    """Resolves each name and port to its fixture instance, and no other name or port."""

    def __init__(self, servers: Mapping[Listener, ServerHandle]) -> None:
        self._servers = servers
        self._lookups: list[str] = []

    @property
    def lookups(self) -> tuple[str, ...]:
        """Each name the resolver was asked, in order, a name that failed included."""
        return tuple(self._lookups)

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        self._lookups.append(host)
        server = self._servers.get((host, port))
        if server is None:
            # As the system resolver fails: aiohttp reports it as ClientConnectorDNSError.
            raise OSError(None, f"the fixture hosts have no name {host} on port {port}")
        address = urlsplit(server.base_url)
        return [
            ResolveResult(
                hostname=host,
                host=address.hostname or "",
                port=address.port or 0,
                family=socket.AF_INET,
                proto=0,
                flags=socket.AI_NUMERICHOST,
            )
        ]

    async def close(self) -> None:
        pass


@dataclass(frozen=True)
class FixtureHosts:
    # site.test and www.site.test
    site: ServerHandle
    # other.test
    other: ServerHandle
    resolver: FixtureResolver


StartHosts = Callable[[Site, Site], FixtureHosts]


@dataclass(frozen=True)
class NamedHosts:
    """A site per host name, such as www.site.test apart from site.test (022 design D9)."""

    servers: Mapping[str, ServerHandle]
    resolver: FixtureResolver


StartNamedHosts = Callable[[Mapping[str, Site]], NamedHosts]


def on_http_port(servers: Mapping[str, ServerHandle]) -> dict[Listener, ServerHandle]:
    return {(name, HTTP_PORT): server for name, server in servers.items()}


def hosts_for(site: ServerHandle, other: ServerHandle) -> FixtureHosts:
    servers = {**dict.fromkeys(SITE_HOSTS, site), OTHER_HOST: other}
    return FixtureHosts(site, other, FixtureResolver(on_http_port(servers)))
