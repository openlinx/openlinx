"""Verify which real CONNECT replies permit an ALPN probe to start TLS."""

import pytest

from tests.fixture_site.routes import Page, Robots, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.proxy import ConnectReply, StartProxy
from tests.support.workspace import TempWorkspace

_SHOP = Site({"/": Page(body="<title>Secure shop</title>")})
_SUCCESS = b"HTTP/1.1 200 Connection Established\r\n"


@pytest.mark.parametrize(
    ("reply", "fetch_error"),
    [
        pytest.param(
            ConnectReply(
                (
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b'Proxy-Authenticate: Basic realm="fixture"\r\n'
                    b"Content-Length: 0\r\n\r\n",
                )
            ),
            "invalid_response",
            id="rejected",
        ),
        pytest.param(
            ConnectReply((b"HTTP/1.1 20X Connection Established\r\n\r\n",)),
            "invalid_response",
            id="malformed-status-line",
        ),
        pytest.param(
            ConnectReply((_SUCCESS + b"Missing-Colon\r\n\r\n",)),
            "invalid_response",
            id="missing-field-colon",
        ),
        pytest.param(
            ConnectReply((_SUCCESS + b"Bad Name: value\r\n\r\n",)),
            "invalid_response",
            id="malformed-field-name",
        ),
        pytest.param(
            ConnectReply((_SUCCESS + b"X-Value: \x00\r\n\r\n",)),
            "invalid_response",
            id="malformed-field-value",
        ),
        pytest.param(
            ConnectReply((_SUCCESS + b"X-Partial: received\r\n",), relay=False),
            "connection_error",
            id="incomplete-header",
        ),
    ],
)
def test_a_failed_connect_probe_preserves_the_ordinary_url_failure(
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    reply: ConnectReply,
    fetch_error: str,
) -> None:
    site = Site({**_SHOP.routes, "/robots.txt": Robots("", headers=[("Connection", "close")])})
    hosts = fixture_tls_hosts(site, Site({}), alpn=("h2", "http/1.1"))
    # Complete replies leave TLS reachable even if they are invalid, so an incorrect probe
    # can negotiate h2 and the test can distinguish it from a correctly refused tunnel.
    proxy = fixture_proxy(hosts.resolver, connect_replies=(ConnectReply(), reply))

    result = crawl_result(
        "https://site.test/",
        proxy=proxy.url,
        trust_anchors=hosts.trust_anchors,
        # robots.txt owns the first tunnel and closes it. The Seed needs a fresh tunnel.
        concurrency=1,
        retries=0,
        network_wait=0,
    )

    assert query(
        result.crawl_file, "SELECT url, fetch_error, status_code, attempt_count FROM urls"
    ) == [("https://site.test/", fetch_error, None, 1)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]
    assert len(proxy.connect_requests) >= 3
    assert [request.path for request in hosts.secure_site.requests] == ["/robots.txt"]


@pytest.mark.parametrize(
    ("size", "version"),
    [(65_536, "http_2"), (65_537, None)],
    ids=["at-limit", "one-byte-over"],
)
def test_connect_header_cap_includes_the_terminating_blank_line(
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    size: int,
    version: str | None,
) -> None:
    hosts = fixture_tls_hosts(_SHOP, Site({}), alpn=("h2", "http/1.1"))
    # Individual lines fit aiohttp's field limits. Only the dedicated probe has the total cap.
    padding = b"X-Pad: " + b"x" * 1015 + b"\r\n"
    prefix = _SUCCESS + padding * 63 + b"X-Tail: "
    tail = b"x" * (size - len(prefix) - 4)
    chunks = (prefix[:32_768], prefix[32_768:] + tail + b"\r\n\r", b"\n")
    assert sum(map(len, chunks)) == size
    proxy = fixture_proxy(hosts.resolver, connect_replies=(ConnectReply(chunks),))

    result = crawl_result(
        "https://site.test/",
        proxy=proxy.url,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert query(
        result.crawl_file, "SELECT url, fetch_error, status_code, attempt_count FROM urls"
    ) == [("https://site.test/", None, 200, 1)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", version)
    ]
    assert len(proxy.connect_requests) == 2
    assert [request.path for request in hosts.secure_site.requests] == ["/robots.txt", "/"]
