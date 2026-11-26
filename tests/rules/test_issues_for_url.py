"""Read one URL's Rule results through the stored and live Issues paths."""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection, Engine, event, update

from openlinx.clock import SystemClock
from openlinx.rules.headings import H1_MISSING
from openlinx.rules.response_codes import INTERNAL_4XX
from openlinx.rules.titles import TITLE_MISSING
from openlinx.store.crawls import read_recorded, record_continue
from openlinx.store.issues import read_url_issues
from openlinx.store.records import UrlIssue
from openlinx.store.schema import pages, urls
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
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
                "/": Page(
                    body='<meta name="description" content="Home"><a href="/present">Present</a>'
                ),
                "/present": Page(
                    body='<title>Present</title><meta name="description" content="Present">'
                    '<a href="/future">Future</a>'
                ),
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


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_live_url_issues_share_one_result_snapshot(
    temp_workspace: TempWorkspace, fixture_site: StartSite, journal_mode: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal_mode}"\n', encoding="utf-8"
    )
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Seed</title><h1>Seed</h1><a href="/other">Other</a>'),
                "/other": Page(
                    body='<meta name="description" content="Other"><a href="/future">Future</a>'
                ),
                "/future": Page(body="<p>Not fetched yet</p>"),
            }
        )
    )
    result = crawl_result(server.url("/"), max_urls=2, concurrency=1)
    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "max_urls")
    file = result.crawl_file
    assert query(file, "PRAGMA journal_mode") == [(journal_mode,)]
    [(url_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/"),))
    [(other_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/other"),))
    catalogue = (H1_MISSING, TITLE_MISSING)
    both = [
        UrlIssue(rule_id="h1-missing", url_id=url_id, detail=None),
        UrlIssue(rule_id="title-missing", url_id=url_id, detail=None),
    ]
    other_issues = [
        UrlIssue(rule_id="h1-missing", url_id=other_id, detail=None),
        UrlIssue(rule_id="title-missing", url_id=other_id, detail=None),
    ]
    assert read_url_issues(file, other_id, catalogue) == other_issues
    reader_thread = threading.get_ident()
    result_statements = 0

    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.flush()
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert read_url_issues(file, other_id, (TITLE_MISSING, H1_MISSING)) == [
            other_issues[1],
            other_issues[0],
        ]
        assert read_url_issues(file, other_id, ()) == []
        assert read_url_issues(file, url_id, catalogue) == []

        def commit_before_title_query(
            connection: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            nonlocal result_statements
            if threading.get_ident() != reader_thread:
                return
            if "pages.h1_count" in statement or "pages.title_count" in statement:
                result_statements += 1
            if "pages.title_count" in statement:
                writer.run(
                    executing(
                        update(pages)
                        .where(pages.c.url_id == url_id)
                        .values(
                            h1_count=0,
                            h1_1=None,
                            h1_1_length=None,
                            title_count=0,
                            title_1=None,
                            title_1_length=None,
                        )
                    )
                )
                writer.flush()

        # Put a real commit between the old per-Rule SELECTs without timing assumptions.
        event.listen(Engine, "before_cursor_execute", commit_before_title_query)
        try:
            during = read_url_issues(file, url_id, catalogue)
        finally:
            event.remove(Engine, "before_cursor_execute", commit_before_title_query)

    assert read_url_issues(file, url_id, catalogue) == both
    assert during == ([] if journal_mode == "wal" else both)
    assert result_statements == 1


def test_one_url_keeps_the_rule_detail_from_each_source(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/gone">Gone</a><a href="/next">Next</a>'),
                "/gone": Status(404),
                "/next": Page(body="<p>Next</p>"),
            }
        )
    )
    result = crawl_result(server.url("/"), max_urls=2, concurrency=1)
    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "max_urls")
    file = result.crawl_file
    [(url_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/gone"),))
    catalogue = (INTERNAL_4XX,)

    # Keep the last Pass at 404 so the reader must use the current row only after Continue.
    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(executing(update(urls).where(urls.c.id == url_id).values(status_code=410)))
        writer.flush()

    assert read_url_issues(file, url_id, catalogue) == [
        UrlIssue(rule_id="internal-4xx", url_id=url_id, detail={"status_code": 404})
    ]

    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.flush()

    assert read_url_issues(file, url_id, catalogue) == [
        UrlIssue(rule_id="internal-4xx", url_id=url_id, detail={"status_code": 410})
    ]
