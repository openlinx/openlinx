"""The units of spider.store.urls (020-add-crawl-core D1, D2, D14; seam 2)."""

from spider.crawl.urls import NormalizedUrl, parse_seed
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def _url(text: str) -> NormalizedUrl:
    url = parse_seed(text)
    assert isinstance(url, str)
    return url


def test_the_units_of_urls_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    seed = _url("https://site.test/")

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(seed, "site.test"))
        writer.run(record_seed(seed, "site.test"))
        writer.run(record_fetched(url_id, 200))
        replay_now(writer)

    assert query(crawl.path, "SELECT id, url, fetch_state, status_code FROM urls") == [
        (url_id, "https://site.test/", "fetched", 200)
    ]
