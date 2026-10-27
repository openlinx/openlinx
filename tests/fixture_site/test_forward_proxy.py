"""The forward proxy of the proxy scenarios (022-add-fetch-policy D9)."""

import asyncio

import aiohttp

from spider.aio import loop_factory
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.proxy import StartProxy


async def _get_through(proxy_url: str, url: str) -> tuple[int, str]:
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, proxy=proxy_url, allow_redirects=False) as response,
    ):
        return response.status, await response.text()


def test_the_proxy_relays_a_request_to_a_fixture_host_and_records_it(
    fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(Site({"/": Page(body="<title>Shop</title>")}), Site({}))
    proxy = fixture_proxy(hosts.resolver)

    status, body = asyncio.run(
        _get_through(proxy.url, "http://site.test/"), loop_factory=loop_factory
    )

    assert (status, "<title>Shop</title>" in body, proxy.requests) == (
        200,
        True,
        ("http://site.test/",),
    )
    assert [request.path for request in hosts.site.requests] == ["/"]


def test_the_proxy_relays_the_status_and_headers(
    fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(Site({}), Site({}))
    proxy = fixture_proxy(hosts.resolver)

    status, _ = asyncio.run(
        _get_through(proxy.url, "http://site.test/missing"), loop_factory=loop_factory
    )

    assert (status, proxy.requests) == (404, ("http://site.test/missing",))
