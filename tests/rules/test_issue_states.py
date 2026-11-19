"""Check how the Issues reader selects a result for the Crawl State."""

import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import Connection, Engine, event, update

from openlinx.rules.titles import TITLE_MISSING, TITLE_TOO_LONG
from openlinx.store.crawls import read_recorded, record_continue, record_state
from openlinx.store.issues import affected_urls_unit, read_affected_urls, read_issues
from openlinx.store.records import AffectedUrl, Issue
from openlinx.store.schema import pages
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing

_AT = datetime(2026, 11, 19, 16, tzinfo=UTC)
_RULES = (TITLE_MISSING,)
_ISSUE = Issue(
    rule_id="title-missing",
    category="titles",
    issue_type="issue",
    priority="high",
    affected_count=1,
)
_STORED = "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'title-missing'"


@pytest.fixture
def stopped_issue(temp_workspace: TempWorkspace, fixture_site: StartSite) -> tuple[Path, int]:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body="<title>Next</title>"),
            }
        )
    )
    seed = server.url("/")
    stopped = crawl_result(seed, max_urls=1, concurrency=1)
    assert (stopped.summary.state, stopped.summary.stop_reason) == ("stopped", "max_urls")
    file = stopped.crawl_file
    [(url_id,)] = query(file, "SELECT id FROM urls WHERE url = ? AND parsed = 1", (seed,))
    assert query(file, _STORED) == [(url_id, None)]
    return file, url_id


def _record_title(writer: CrawlWriter, url_id: int) -> None:
    writer.run(
        executing(
            update(pages)
            .where(pages.c.url_id == url_id)
            .values(title_count=1, title_1="Shoes", title_1_length=5)
        )
    )


def test_a_crawl_without_a_final_pass_is_read_live(stopped_issue: tuple[Path, int]) -> None:
    file, url_id = stopped_issue
    with CrawlWriter(file, FakeClock()) as writer:
        # Keep the Page and the previous pass different, so either fixed choice fails.
        _record_title(writer, url_id)
        writer.flush()
        assert read_issues(file, _RULES) == [_ISSUE]
        assert read_affected_urls(file, "title-missing", _RULES) == [
            AffectedUrl(url_id=url_id, detail=None)
        ]

        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.run(record_state("failed", _AT, "site_unreachable"))
        writer.flush()

    assert query(file, "SELECT state, stop_reason FROM crawl") == [("failed", "site_unreachable")]
    assert query(file, "SELECT title_1 FROM pages WHERE url_id = ?", (url_id,)) == [("Shoes",)]
    assert query(file, _STORED) == [(url_id, None)]
    assert read_issues(file, _RULES) == []
    assert read_affected_urls(file, "title-missing", _RULES) == []


@pytest.fixture
def completed_issues(temp_workspace: TempWorkspace, fixture_site: StartSite) -> tuple[Path, str]:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Seed</title><a href="/a">A</a><a href="/b">B</a>'),
                "/a": Page(body="<p>A</p>"),
                "/b": Page(body="<p>B</p>"),
            }
        )
    )
    result = crawl_result(server.url("/"))
    assert result.summary.state == "completed"
    return result.crawl_file, server.url("/")


@pytest.mark.parametrize("result", ["issues", "affected_urls"])
@pytest.mark.parametrize("installed_version", ["needs_new_column", "missing"])
def test_completed_crawl_reads_its_own_issues(
    completed_issues: tuple[Path, str],
    result: Literal["issues", "affected_urls"],
    installed_version: Literal["needs_new_column", "missing"],
) -> None:
    file, root = completed_issues
    current = replace(
        TITLE_MISSING,
        priority="low",
        reproduce_sql="SELECT url_id, pages.future_title_field AS detail FROM pages",
    )
    catalogue = (current,) if installed_version == "needs_new_column" else (TITLE_TOO_LONG,)

    if result == "issues":
        assert read_issues(file, catalogue) == [
            Issue(
                rule_id="title-missing",
                category="titles",
                issue_type="issue",
                priority="high",
                affected_count=2,
            )
        ]
    else:
        urls = read_affected_urls(file, "title-missing", catalogue)
        by_id = dict(query(file, "SELECT id, url FROM urls"))
        assert sorted((by_id[url.url_id], url.detail) for url in urls) == [
            (root + "a", None),
            (root + "b", None),
        ]


@pytest.mark.parametrize("result", ["issues", "affected_urls"])
def test_issue_state_and_result_share_a_snapshot(
    stopped_issue: tuple[Path, int], result: Literal["issues", "affected_urls"]
) -> None:
    file, url_id = stopped_issue
    assert query(file, "PRAGMA journal_mode") == [("wal",)]
    reader_thread = threading.get_ident()
    committed = False

    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.flush()
        assert query(file, "SELECT state FROM crawl") == [("running",)]

        def finish_after_select(
            connection: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            nonlocal committed
            if (
                threading.get_ident() == reader_thread
                and not committed
                and statement.lstrip().upper().startswith("SELECT")
            ):
                committed = True
                _record_title(writer, url_id)
                writer.run(affected_urls_unit(TITLE_MISSING))
                writer.run(record_state("stopped", _AT, "requested"))
                writer.flush()

        # The real commit lands at the first SELECT boundary. A second unpinned SELECT
        # can see the new Page together with a Crawl State read before the commit.
        event.listen(Engine, "after_cursor_execute", finish_after_select)
        try:
            if result == "issues":
                assert read_issues(file, _RULES) == [_ISSUE]
            else:
                assert read_affected_urls(file, "title-missing", _RULES) == [
                    AffectedUrl(url_id=url_id, detail=None)
                ]
        finally:
            event.remove(Engine, "after_cursor_execute", finish_after_select)

    assert committed
    assert query(file, "SELECT state, stop_reason FROM crawl") == [("stopped", "requested")]
    assert query(file, _STORED) == []
    assert read_issues(file, _RULES) == []
    assert read_affected_urls(file, "title-missing", _RULES) == []
