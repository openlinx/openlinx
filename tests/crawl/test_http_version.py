"""Verify the HTTP capability recorded by a Crawl of real fixture origins."""

import asyncio
import socket
import sqlite3
import ssl
from contextlib import closing
from pathlib import Path
from typing import Literal

import pytest
import trustme
from aiohttp.abc import ResolveResult

from openlinx.services.crawling import CrawlOverrides
from openlinx.store.records import HttpVersion
from tests.fixture_site.hosts import FixtureResolver, StartHosts
from tests.fixture_site.routes import Page, Redirect, Robots, Site, Status
from tests.fixture_site.server import Serve, ServerHandle
from tests.fixture_site.tls import SniLog, StartTlsHosts
from tests.support.alpn import with_wrong_name_for_probe
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SITE = Site({"/": Page(body='<a href="http://other.test/partner">Partner</a>')})
OTHER = Site({"/partner": Page(body="<title>Partner</title>")})


def test_an_origin_that_selects_http_2(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Home</title>")}), OTHER, alpn=("h2", "http/1.1")
    )

    result = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    requests = hosts.secure_site.requests
    assert [(request.method, request.path, request.http_version) for request in requests] == [
        ("GET", "/robots.txt", (1, 1)),
        ("GET", "/", (1, 1)),
    ]
    assert all(request.alpn != "h2" for request in requests)
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]


def test_an_origin_that_offers_only_http_1_1(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    crawl_file = _crawl_https(fixture_tls_hosts, alpn=("http/1.1",))

    assert query(crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_1_1")
    ]


@pytest.mark.parametrize("seed", ["https://site.test./", "https://site.test../"])
def test_an_absolute_origin_name_keeps_its_dns_root(
    temp_workspace: TempWorkspace, fixture_site: Serve, seed: str
) -> None:
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert("site.test").configure_cert(tls)
    tls.set_alpn_protocols(["h2", "http/1.1"])
    sni = SniLog()
    tls.sni_callback = sni.record
    site = fixture_site(Site({"/": Page(body="<title>Home</title>")}), tls)
    resolver = FixtureResolver({("site.test.", 443): site})

    result = crawl_result(
        seed,
        resolver=resolver,
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        retries=0,
        network_wait=0,
    )

    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [(seed, 200)]
    assert query(result.crawl_file, "SELECT http_version FROM origins") == [("http_2",)]
    assert resolver.lookups == ("site.test.", "site.test.")
    assert sni.names == ("site.test", "site.test")


def test_a_listener_with_no_alpn_selection_is_http_1_1_capable(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    crawl_file = _crawl_https(fixture_tls_hosts, alpn=())

    assert query(crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_1_1")
    ]


def _crawl_https(fixture_tls_hosts: StartTlsHosts, *, alpn: tuple[str, ...]) -> Path:
    hosts = fixture_tls_hosts(Site({"/": Page(body="<title>Home</title>")}), OTHER, alpn=alpn)
    result = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    return result.crawl_file


def test_one_failed_probe_is_not_repeated_for_another_url(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    site = Site(
        {
            "/": Page(body='<a href="/a">A</a><a href="/b">B</a>'),
            "/a": Page(body="<p>A</p>", after="/b"),
            "/b": Page(body="<p>B</p>", after="/a"),
        }
    )
    hosts = fixture_tls_hosts(site, OTHER)

    result = crawl_result(
        "https://site.test/",
        fetchers=with_wrong_name_for_probe(hosts),
        concurrency=2,
        network_wait=0,
        retries=0,
    )

    assert result.summary.state == "completed"
    assert hosts.secure_site.most_simultaneous == 2
    assert query(result.crawl_file, "SELECT url, status_code FROM urls ORDER BY url") == [
        ("https://site.test/", 200),
        ("https://site.test/a", 200),
        ("https://site.test/b", 200),
    ]
    assert hosts.badcert.requests == ()
    assert hosts.badcert_sni.names == ("site.test",)
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_ignoring_robots_does_not_skip_capability_measurement(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    site = Site(
        {
            "/": Page(body="<title>Home</title>"),
            "/robots.txt": Status(503),
        }
    )
    hosts = fixture_tls_hosts(site, OTHER, alpn=("h2", "http/1.1"))

    result = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        ignore_robots=True,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert [request.path for request in hosts.secure_site.requests] == ["/robots.txt", "/"]
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    assert query(
        result.crawl_file,
        "SELECT origin, robots_state, robots_status_code, http_version FROM origins",
    ) == [("https://site.test", "unreachable", 503, "http_2")]


def test_an_external_origin_is_measured(temp_workspace: TempWorkspace, fixture_site: Serve) -> None:
    site = fixture_site(Site({"/": Page(body='<a href="https://other.test/page">Partner</a>')}))
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert("other.test").configure_cert(tls)
    tls.set_alpn_protocols(["h2", "http/1.1"])
    other = fixture_site(Site({"/page": Page(body="<title>Partner</title>")}), tls)
    resolver = FixtureResolver({("site.test", 80): site, ("other.test", 443): other})

    result = crawl_result(
        "http://site.test/",
        resolver=resolver,
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        check_external=True,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert query(
        result.crawl_file, "SELECT url, is_internal, status_code FROM urls ORDER BY url"
    ) == [("http://site.test/", 1, 200), ("https://other.test/page", 0, 200)]
    assert query(
        result.crawl_file, "SELECT origin, is_internal, http_version FROM origins ORDER BY origin"
    ) == [("http://site.test", 1, "http_1_1"), ("https://other.test", 0, "http_2")]


class _RobotsRedirectResolver(FixtureResolver):
    def __init__(self, servers: dict[tuple[str, int], ServerHandle], *, tls: bool) -> None:
        super().__init__(servers)
        self._tls = tls
        self._probe: asyncio.Task[object] | None = None
        self._probe_started = asyncio.Event()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        if host == "other.test" and port == 443 and host in self.lookups:
            # The ordinary request resolved this name to reach /remote-rules. Its dedicated
            # probe resolves it again, with the ordinary session's route already cached.
            self._probe = asyncio.current_task()
            self._probe_started.set()
        if self._tls and host == "rules.test":
            # For HTTPS the last robots hop waits for the real TLS task to finish. The Seed
            # is still waiting on robots.txt, so its Link cannot have been recorded yet.
            await self._probe_started.wait()
            assert self._probe is not None
            await asyncio.wait({self._probe})
        return await super().resolve(host, port, family)


@pytest.mark.parametrize(
    ("scheme", "capability", "check_external"),
    [("http", "http_1_1", False), ("https", "http_2", True)],
)
def test_robots_redirect_capability_survives_late_url_discovery(
    temp_workspace: TempWorkspace,
    fixture_site: Serve,
    scheme: Literal["http", "https"],
    capability: HttpVersion,
    check_external: bool,
) -> None:
    target = f"{scheme}://other.test"
    site = fixture_site(
        Site(
            {
                "/robots.txt": Redirect(f"{target}/remote-rules"),
                "/": Page(body=f'<a href="{target}/page">Partner</a>'),
            }
        )
    )
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert("other.test").configure_cert(tls)
    tls.set_alpn_protocols(["h2", "http/1.1"])
    other = fixture_site(
        Site(
            {
                "/remote-rules": Redirect("http://rules.test/allow"),
                "/robots.txt": Status(404),
                "/page": Page(body="<title>Partner</title>"),
            }
        ),
        tls if scheme == "https" else None,
    )
    rules = fixture_site(Site({"/allow": Robots("User-agent: *\nAllow: /\n")}))
    resolver = _RobotsRedirectResolver(
        {
            ("site.test", 80): site,
            ("other.test", 443 if scheme == "https" else 80): other,
            ("rules.test", 80): rules,
        },
        tls=scheme == "https",
    )

    result = crawl_result(
        "http://site.test/",
        resolver=resolver,
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        check_external=check_external,
        concurrency=2,
        retries=0,
        network_wait=0,
        timeout=10,
    )

    assert result.summary.state == "completed"
    assert [request.path for request in site.requests] == ["/robots.txt", "/"]
    assert [request.path for request in rules.requests] == ["/allow"]
    assert [request.path for request in other.requests] == (
        ["/remote-rules", "/robots.txt", "/page"] if check_external else ["/remote-rules"]
    )
    assert resolver.lookups.count("other.test") == (2 if check_external else 1)
    assert query(
        result.crawl_file,
        "SELECT url, discovered_via, status_code, attempt_count, skip_reason FROM urls ORDER BY id",
    ) == [
        ("http://site.test/", "seed", 200, 1, None),
        (
            f"{target}/page",
            "hyperlink",
            200 if check_external else None,
            1 if check_external else 0,
            None if check_external else "external_not_checked",
        ),
    ]
    assert query(
        result.crawl_file,
        "SELECT origin, host, is_internal, robots_state, robots_status_code, http_version "
        "FROM origins ORDER BY id",
    ) == [
        ("http://site.test", "site.test", 1, "ok", 200, "http_1_1"),
        (
            target,
            "other.test",
            0,
            "missing" if check_external else None,
            404 if check_external else None,
            capability,
        ),
    ]


def test_probe_failure_leaves_url_requests_unchanged(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    site = Site(
        {
            "/": Page(body='<a href="/child">Child</a>'),
            "/child": Page(body="<title>Child</title>"),
        }
    )
    hosts = fixture_tls_hosts(site, OTHER)

    result = crawl_result(
        "https://site.test/",
        fetchers=with_wrong_name_for_probe(hosts),
        concurrency=1,
        max_urls=2,
        network_wait=0,
        retries=0,
    )

    assert result.summary.state == "completed"
    assert hosts.badcert_sni.names == ("site.test",)
    assert hosts.badcert.requests == ()
    assert [request.path for request in hosts.secure_site.requests] == [
        "/_warmup",
        "/robots.txt",
        "/",
        "/child",
    ]
    assert query(
        result.crawl_file,
        "SELECT url, status_code, attempt_count, fetch_error FROM urls ORDER BY url",
    ) == [("https://site.test/", 200, 1, None), ("https://site.test/child", 200, 1, None)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_a_failed_capability_probe_does_not_trigger_the_network_pause(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    # After the plain HTTP Seed answers, the HTTPS origin gets a probe and seven URL
    # requests without a usable response. An eighth failure would trip the network pause.
    downs = [f"/down/{number}" for number in range(1, 8)]
    links = "".join(f'<a href="https://site.test{path}">Down</a>' for path in downs)
    site = Site(
        {
            "/": Page(body=links),
            **{path: Page(body="<p>Down</p>", reset_after=0) for path in downs},
        }
    )
    hosts = fixture_tls_hosts(site, OTHER)

    result = crawl_result(
        "http://site.test/",
        fetchers=with_wrong_name_for_probe(hosts),
        concurrency=1,
        network_wait=0,
        retries=0,
    )

    assert result.summary.state == "completed"
    assert hosts.badcert_sni.names == ("site.test",)
    assert query(
        result.crawl_file,
        "SELECT fetch_state, status_code, attempt_count, COUNT(*) FROM urls "
        "GROUP BY 1, 2, 3 ORDER BY 1",
    ) == [("error", None, 1, 7), ("fetched", 200, 1, 1)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins ORDER BY origin") == [
        ("http://site.test", "http_1_1"),
        ("https://site.test", None),
    ]


def test_a_failed_probe_on_continue_clears_the_earlier_capability(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    site = Site(
        {
            "/": Page(body='<a href="/middle">Middle</a>'),
            "/middle": Page(body='<a href="/last">Last</a>'),
            "/last": Page(body="<title>Last</title>"),
        }
    )
    hosts = fixture_tls_hosts(site, OTHER, alpn=("h2", "http/1.1"))
    stopped = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        concurrency=1,
        max_urls=2,
        network_wait=0,
        retries=0,
    )
    assert stopped.summary.state == "stopped"
    assert stopped.summary.stop_reason == "max_urls"
    assert query(stopped.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]

    result = continued(
        stopped, CrawlOverrides(max_urls=None), fetchers=with_wrong_name_for_probe(hosts)
    )

    assert result.summary.state == "completed"
    assert hosts.badcert_sni.names == ("site.test",)
    assert query(
        result.crawl_file, "SELECT url, status_code, attempt_count FROM urls ORDER BY url"
    ) == [
        ("https://site.test/", 200, 1),
        ("https://site.test/last", 200, 1),
        ("https://site.test/middle", 200, 1),
    ]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_a_plain_http_origin(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    proxy = fixture_proxy(hosts.resolver)

    result = crawl_result(
        "http://site.test/",
        proxy=proxy.url,
        check_external=False,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert proxy.requests == ("http://site.test/robots.txt", "http://site.test/")
    assert proxy.connect_requests == ()
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins ORDER BY origin") == [
        ("http://other.test", None),
        ("http://site.test", "http_1_1"),
    ]
    assert query(result.crawl_file, "SELECT http_version FROM pages") == [(None,)]


def test_continuing_a_crawl_with_unmeasured_origins_records_only_newly_requested_ones(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    stopped = crawl_result(
        "http://site.test/", resolver=hosts.resolver, max_urls=1, retries=0, network_wait=0
    )
    assert (
        stopped.summary.state,
        stopped.summary.stop_reason,
        [request.path for request in hosts.other.requests],
    ) == ("stopped", "max_urls", [])
    # Schema v1 already had the column; a Crawl written before measurement held NULL in it.
    with closing(sqlite3.connect(stopped.crawl_file)) as connection:
        connection.execute("UPDATE origins SET http_version = NULL")
        connection.commit()

    result = continued(stopped, CrawlOverrides(max_urls=None), resolver=hosts.resolver)

    assert result.summary.state == "completed"
    assert [request.path for request in hosts.site.requests] == ["/robots.txt", "/"]
    assert [request.path for request in hosts.other.requests] == ["/robots.txt", "/partner"]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins ORDER BY origin") == [
        ("http://other.test", "http_1_1"),
        ("http://site.test", None),
    ]
    assert query(result.crawl_file, "SELECT schema_version FROM crawl") == [(1,)]
    assert query(result.crawl_file, "PRAGMA user_version") == [(1,)]
