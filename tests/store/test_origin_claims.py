"""Exercise the run-local HTTP version queue through the Crawl writer."""

from openlinx.store.origins import (
    claim_http_version,
    init_http_version_claims,
    next_http_version_claim,
)
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
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
