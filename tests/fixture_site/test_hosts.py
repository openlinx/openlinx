"""The DNS resolver hook: fixture host names for multi-host Crawls (020-add-crawl-core D15)."""

import aiohttp
import pytest

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site

SITE = Site(routes={"/": Page(body="<p>Site</p>"), "/x": Page(body="<p>X</p>")})
OTHER = Site(routes={"/y": Page(body="<p>Other</p>")})


async def test_site_names_reach_the_first_instance_and_other_test_the_second(
    fixture_hosts: StartHosts,
) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        for url in ("http://site.test/", "http://www.site.test/x", "http://other.test/y"):
            async with session.get(url) as response:
                assert response.status == 200

    assert (
        [request.path for request in hosts.site.requests],
        [request.path for request in hosts.other.requests],
    ) == (["/", "/x"], ["/y"])


async def test_every_other_name_is_a_dns_error(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        with pytest.raises(aiohttp.ClientConnectorDNSError):
            await session.get("http://nowhere.test/")


async def test_the_resolver_logs_each_name_it_is_asked(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver, use_dns_cache=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("http://site.test/") as response:
            await response.read()
        with pytest.raises(aiohttp.ClientConnectorDNSError):
            await session.get("http://nowhere.test/")

    assert hosts.resolver.lookups == ("site.test", "nowhere.test")
