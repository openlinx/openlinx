"""Keep sensitive request headers out of transport failures recorded by the Crawl Service."""

import socket

from aiohttp.abc import AbstractResolver, ResolveResult

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


class QuotingResolver(AbstractResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise OSError(None, "refused abc123; environment staging")

    async def close(self) -> None:
        pass


def test_a_dns_failure_hides_sensitive_header_values_in_url_and_robots_records(
    temp_workspace: TempWorkspace,
) -> None:
    result = crawl_result(
        "http://site.test/",
        resolver=QuotingResolver(),
        header=["X-Env: staging", "X-Token: abc123", "X-Env: audit"],
        retries=0,
        network_wait=0,
    )

    [(fetch_error, message)] = query(
        result.crawl_file,
        "SELECT fetch_error, fetch_error_message FROM urls WHERE url = 'http://site.test/'",
    )
    [(robots_error, robots_message)] = query(
        result.crawl_file,
        "SELECT robots_fetch_error, robots_fetch_error_message FROM origins "
        "WHERE origin = 'http://site.test'",
    )
    assert fetch_error == "dns_error"
    assert "refused ***; environment staging" in message
    assert "abc123" not in message
    assert robots_error == "dns_error"
    assert "refused ***; environment staging" in robots_message
    assert "abc123" not in robots_message


def test_a_url_transport_failure_hides_sensitive_header_values(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="Home", headers=[("X-abc123 bad", "staging")])}))

    result = crawl_result(server.url("/"), header=["X-Token: abc123"], retries=0, network_wait=0)

    [(fetch_error, message)] = query(
        result.crawl_file,
        "SELECT fetch_error, fetch_error_message FROM urls WHERE url = ?",
        [server.url("/")],
    )
    assert fetch_error == "invalid_response"
    assert "X-*** bad: staging" in message
    assert "abc123" not in message
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]
