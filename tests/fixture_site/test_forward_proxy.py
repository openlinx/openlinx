"""Verify the local forward proxy used by HTTP proxy scenarios."""

import asyncio
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import aiohttp
import pytest

from openlinx.aio import loop_factory
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.proxy import ForwardProxy, StartProxy


async def _get_through(
    proxy_url: str, url: str, context: ssl.SSLContext | bool = True
) -> tuple[int, str]:
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, proxy=proxy_url, ssl=context, allow_redirects=False) as response,
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


def test_the_proxy_tunnels_https_and_records_connect_separately(
    fixture_tls_hosts: StartTlsHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_tls_hosts(Site({"/": Page(body="<title>Secure shop</title>")}), Site({}))
    proxy = fixture_proxy(hosts.resolver, auth=("u", "pw"))
    with_password = proxy.url.replace("http://", "http://u:pw@")

    status, body = asyncio.run(
        _get_through(
            with_password,
            "https://site.test/",
            ssl.create_default_context(cadata=hosts.trust_anchors),
        ),
        loop_factory=loop_factory,
    )

    assert (
        status,
        body,
        [
            (entry.method, entry.target, entry.headers.get("Proxy-Authorization"))
            for entry in proxy.connect_requests
        ],
        proxy.requests,
        [
            (request.path, request.headers.get("Proxy-Authorization"))
            for request in hosts.secure_site.requests
        ],
    ) == (
        200,
        "<title>Secure shop</title>",
        [("CONNECT", "site.test:443", "Basic dTpwdw==")],
        (),
        [("/", None)],
    )


@pytest.mark.parametrize(
    ("credentials", "authorization"), [("", None), ("u:wrong@", "Basic dTp3cm9uZw==")]
)
def test_the_proxy_refuses_missing_or_wrong_tunnel_credentials(
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    credentials: str,
    authorization: str | None,
) -> None:
    hosts = fixture_tls_hosts(Site({"/": Page(body="Secure shop")}), Site({}))
    proxy = fixture_proxy(hosts.resolver, auth=("u", "pw"))
    proxy_url = proxy.url.replace("http://", f"http://{credentials}")

    with pytest.raises(aiohttp.ClientHttpProxyError) as caught:
        asyncio.run(
            _get_through(
                proxy_url,
                "https://site.test/",
                ssl.create_default_context(cadata=hosts.trust_anchors),
            ),
            loop_factory=loop_factory,
        )

    assert (
        caught.value.status,
        [
            (entry.method, entry.target, entry.headers.get("Proxy-Authorization"))
            for entry in proxy.connect_requests
        ],
        hosts.secure_site.requests,
        hosts.resolver.lookups,
    ) == (407, [("CONNECT", "site.test:443", authorization)], (), ())


def test_stopping_the_proxy_closes_idle_tunnels_and_partial_requests(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(Site({}), Site({}))
    with ThreadPoolExecutor(max_workers=1) as executor:
        proxy = ForwardProxy(hosts.resolver)
        address = urlsplit(proxy.url)
        stopping = None
        try:
            with (
                socket.create_connection(("127.0.0.1", address.port or 0), timeout=2) as tunnel,
                socket.create_connection(("127.0.0.1", address.port or 0), timeout=2) as partial,
            ):
                tunnel.sendall(b"CONNECT site.test:443 HTTP/1.1\r\nHost: site.test:443\r\n\r\n")
                with tunnel.makefile("rb") as response:
                    assert response.readline() == b"HTTP/1.1 200 Connection Established\r\n"
                    assert response.readline() == b"\r\n"
                partial.sendall(b"CONNECT site.test:443 HTTP/1.1\r\n")

                stopping = executor.submit(proxy.stop)

                assert (tunnel.recv(1), partial.recv(1)) == (b"", b"")
        finally:
            if stopping is None:
                proxy.stop()
            else:
                stopping.result(timeout=5)


def test_the_proxy_relays_the_status_and_headers(
    fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(
        Site({"/old": Page(body="Moved", headers=[("X-Served-By", "shop-1")])}), Site({})
    )
    proxy = fixture_proxy(hosts.resolver)
    with_password = proxy.url.replace("http://", "http://u:pw@")

    found = asyncio.run(
        _head_through(with_password, "http://site.test/old"), loop_factory=loop_factory
    )
    missing, _ = asyncio.run(
        _get_through(proxy.url, "http://site.test/missing"), loop_factory=loop_factory
    )

    # The site never sees the proxy's own credentials.
    assert (found, missing, hosts.site.requests[0].headers.get("Proxy-Authorization")) == (
        (200, "shop-1"),
        404,
        None,
    )


async def _head_through(proxy_url: str, url: str) -> tuple[int, str | None]:
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, proxy=proxy_url, allow_redirects=False) as response,
    ):
        return response.status, response.headers.get("X-Served-By")
