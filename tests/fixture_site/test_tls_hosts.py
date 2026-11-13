"""HTTPS listeners with a test CA, behind the DNS resolver hook (022-add-fetch-policy D5)."""

import ssl

import aiohttp
import pytest

from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts

SITE = Site(routes={"/": Page(body="<p>Site</p>")})
OTHER = Site(routes={"/": Page(body="<p>Other</p>")})


async def test_each_https_listener_serves_the_certificate_it_is_named_for(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)
    trusted = ssl.create_default_context(cadata=hosts.trust_anchors)
    untrusted = ssl.create_default_context(cadata=hosts.untrusted_anchors)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        for url, context, certificate_name in (
            ("http://site.test/", True, None),
            ("https://site.test/", trusted, None),
            ("https://www.site.test/", trusted, None),
            ("https://badcert.test/", trusted, "other.test"),
            (f"https://other.test:{hosts.untrusted_port}/", untrusted, None),
        ):
            async with session.get(url, ssl=context, server_hostname=certificate_name) as response:
                assert response.status == 200

    assert [
        len(server.requests)
        for server in (hosts.site, hosts.secure_site, hosts.badcert, hosts.untrusted)
    ] == [1, 2, 1, 1]


async def test_a_name_is_resolved_only_on_the_ports_it_listens_on(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        for url in ("http://badcert.test/", "https://other.test/", "http://site.test:8080/"):
            with pytest.raises(aiohttp.ClientConnectorDNSError):
                await session.get(url)
