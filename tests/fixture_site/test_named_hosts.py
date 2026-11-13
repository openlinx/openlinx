"""A site per host name behind the DNS resolver hook (022-add-fetch-policy D9)."""

import aiohttp

from tests.fixture_site.hosts import StartNamedHosts
from tests.fixture_site.routes import Page, Redirect, Site


async def test_each_name_reaches_its_own_site(fixture_named_hosts: StartNamedHosts) -> None:
    # The www host of a shop redirects to its apex: two sites, so the redirect cannot loop.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/")}),
            "site.test": Site({"/": Page(body="<title>Shop</title>")}),
        }
    )
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("http://www.site.test/", allow_redirects=False) as moved:
            location = moved.headers["Location"]
        async with session.get(location) as page:
            body = await page.text()

    assert (
        location,
        "<title>Shop</title>" in body,
        [request.path for request in hosts.servers["www.site.test"].requests],
        [request.path for request in hosts.servers["site.test"].requests],
    ) == ("http://site.test/", True, ["/"], ["/"])
