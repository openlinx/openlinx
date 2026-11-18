"""Exercise the run-local HTTP version queue through the Crawl writer."""

import pytest

from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.origins import (
    claim_http_version,
    init_http_version_claims,
    next_http_version_claim,
    record_http_version,
)
from openlinx.store.records import HttpVersion
from openlinx.store.urls import record_seed
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_origin_claims_are_deduplicated_through_replay_and_reset_on_a_new_writer(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)
    with CrawlWriter(crawl.path, FakeClock(), disk_temp_store=True) as writer:
        writer.run(init_http_version_claims)
        assert writer.run(claim_http_version("https://site.test", 10.0)) is True
        replay_now(writer)
        assert writer.run(claim_http_version("https://site.test", 20.0)) is False
        assert writer.run(claim_http_version("https://other.test", 11.0)) is True
        assert writer.run(next_http_version_claim(0)) == (1, "https://site.test", 10.0)
        assert writer.run(next_http_version_claim(1)) == (2, "https://other.test", 11.0)
        assert writer.run(next_http_version_claim(2)) is None

    with CrawlWriter(crawl.path, FakeClock(), disk_temp_store=True) as writer:
        writer.run(init_http_version_claims)
        assert writer.run(next_http_version_claim(0)) is None
        assert writer.run(claim_http_version("https://site.test", 20.0)) is True
        assert writer.run(next_http_version_claim(0)) == (1, "https://site.test", 20.0)


@pytest.mark.parametrize(("scheme", "capability"), [("http", "http_1_1"), ("https", "http_2")])
def test_a_measurement_outlives_replay_before_and_during_origin_discovery(
    temp_workspace: TempWorkspace, scheme: str, capability: HttpVersion
) -> None:
    origin = f"{scheme}://site.test"
    url = NormalizedUrl(f"{origin}/")
    crawl = create_any_crawl(temp_workspace, seeds=[url])

    with CrawlWriter(crawl.path, FakeClock(), disk_temp_store=True) as writer:
        writer.run(init_http_version_claims)
        if scheme == "https":
            assert writer.run(claim_http_version(origin, 10.0)) is True
        writer.run(record_http_version(origin, capability))
        replay_now(writer)
        assert query(crawl.path, "SELECT origin FROM origins") == []

        writer.run(record_seed(url, is_internal=True, in_scope=True))
        replay_now(writer)
        assert query(crawl.path, "SELECT origin, host, is_internal, http_version FROM origins") == [
            (origin, "site.test", 1, capability)
        ]
        assert query(
            crawl.path,
            "SELECT urls.url, origins.origin FROM urls JOIN origins ON origins.id = urls.origin_id",
        ) == [(url, origin)]

        if scheme == "https":
            assert writer.run(claim_http_version(origin, 20.0)) is False
        else:
            assert writer.run(next_http_version_claim(0)) is None
