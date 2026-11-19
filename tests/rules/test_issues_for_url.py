"""Read one URL's Rule results through the stored and live Issues paths."""

from datetime import UTC, datetime

from sqlalchemy import update

from openlinx.clock import SystemClock
from openlinx.rules.titles import TITLE_MISSING
from openlinx.store.crawls import read_recorded, record_continue
from openlinx.store.issues import read_url_issues
from openlinx.store.records import UrlIssue
from openlinx.store.schema import pages
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing

_AT = datetime(2026, 11, 19, 16, tzinfo=UTC)
_CATALOGUE = (TITLE_MISSING,)


def test_one_url_reads_stored_then_live_issues(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/present">Present</a>'),
                "/present": Page(body='<title>Present</title><a href="/future">Future</a>'),
                "/future": Page(body="<p>Not fetched yet</p>"),
            }
        )
    )
    result = crawl_result(server.url("/"), max_urls=2, concurrency=1)
    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "max_urls")
    file = result.crawl_file
    [(root_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/"),))
    [(present_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/present"),))
    assert query(file, "SELECT url, fetch_state FROM urls ORDER BY id") == [
        (server.url("/"), "fetched"),
        (server.url("/present"), "fetched"),
        (server.url("/future"), "queued"),
    ]

    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(
            executing(
                update(pages)
                .where(pages.c.url_id == root_id)
                .values(title_count=1, title_1="Present", title_1_length=7)
            )
        )
        writer.run(
            executing(
                update(pages)
                .where(pages.c.url_id == present_id)
                .values(title_count=0, title_1=None, title_1_length=None)
            )
        )
        writer.flush()

    assert read_url_issues(file, root_id, _CATALOGUE) == [
        UrlIssue(rule_id="title-missing", url_id=root_id, detail=None),
        UrlIssue(rule_id="h1-missing", url_id=root_id, detail=None),
    ]
    assert read_url_issues(file, present_id, _CATALOGUE) == [
        UrlIssue(rule_id="h1-missing", url_id=present_id, detail=None)
    ]

    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.flush()

    assert read_url_issues(file, root_id, _CATALOGUE) == []
    assert read_url_issues(file, present_id, _CATALOGUE) == [
        UrlIssue(rule_id="title-missing", url_id=present_id, detail=None)
    ]
