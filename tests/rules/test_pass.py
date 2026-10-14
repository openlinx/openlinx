"""The units of the Issues pass (040-add-rules D5, D15; seam 2)."""

from spider.rules.titles import TITLE_MISSING
from spider.store.issues import affected_urls_unit
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import query
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_the_issues_pass_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        writer.run(affected_urls_unit(TITLE_MISSING))
        writer.run(affected_urls_unit(TITLE_MISSING))
        replay_now(writer)

    assert query(crawl_file, "SELECT rule_id, url_id, detail FROM affected_urls") == [
        ("title-missing", url_id, None)
    ]
