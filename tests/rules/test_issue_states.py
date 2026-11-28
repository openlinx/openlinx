"""Check how the Issues reader selects a result for the Crawl State."""

import asyncio
import re
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import Connection, Engine, event, select, update

from openlinx.output.diagnostics import OpenLinxError
from openlinx.rules.model import Rule
from openlinx.rules.titles import TITLE_MISSING, TITLE_TOO_LONG
from openlinx.store.crawls import read_recorded, record_continue, record_state
from openlinx.store.issues import (
    affected_urls_in,
    affected_urls_unit,
    evaluate_rule,
    issues_in,
    materialise_issues,
    read_affected_urls,
    read_issues,
    read_url_issues,
)
from openlinx.store.reading import reading
from openlinx.store.records import AffectedUrl, Issue, UrlIssue
from openlinx.store.schema import pages, rules
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.rules import PREVIEW_NO_ROWS, PREVIEW_RULE_IDS
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


def _title_missing_issues(file: Path, catalogue: tuple[Rule, ...]) -> list[Issue]:
    return [issue for issue in read_issues(file, catalogue) if issue.rule_id == "title-missing"]


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


def test_stored_issue_counts_seek_only_the_requested_rules(stopped_issue: tuple[Path, int]) -> None:
    file, _ = stopped_issue
    with reading(file) as connection:
        counts = issues_in(connection, _RULES, rule_ids=frozenset({"title-missing"}))
        sql = counts.compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
        plan = connection.exec_driver_sql(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        assert connection.execute(counts).all() == [("title-missing", "titles", "issue", "high", 1)]

    assert any("SEARCH affected_urls USING PRIMARY KEY" in row[3] for row in plan), plan


def test_a_crawl_without_a_final_pass_is_read_live(stopped_issue: tuple[Path, int]) -> None:
    file, url_id = stopped_issue
    with CrawlWriter(file, FakeClock()) as writer:
        # Keep the Page and the previous pass different, so either fixed choice fails.
        _record_title(writer, url_id)
        writer.flush()
        assert _title_missing_issues(file, _RULES) == [_ISSUE]
        assert read_affected_urls(file, "title-missing", _RULES) == [
            AffectedUrl(url_id=url_id, detail=None)
        ]

        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.run(record_state("failed", _AT, "site_unreachable"))
        writer.flush()

    assert query(file, "SELECT state, stop_reason FROM crawl") == [("failed", "site_unreachable")]
    assert query(file, "SELECT title_1 FROM pages WHERE url_id = ?", (url_id,)) == [("Shoes",)]
    assert query(file, _STORED) == [(url_id, None)]
    assert _title_missing_issues(file, _RULES) == []
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
        assert _title_missing_issues(file, catalogue) == [
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
                assert _title_missing_issues(file, _RULES) == [_ISSUE]
            else:
                assert read_affected_urls(file, "title-missing", _RULES) == [
                    AffectedUrl(url_id=url_id, detail=None)
                ]
        finally:
            event.remove(Engine, "after_cursor_execute", finish_after_select)

    assert committed
    assert query(file, "SELECT state, stop_reason FROM crawl") == [("stopped", "requested")]
    assert query(file, _STORED) == []
    assert _title_missing_issues(file, _RULES) == []
    assert read_affected_urls(file, "title-missing", _RULES) == []


@pytest.mark.parametrize("stored", [False, True], ids=["live", "stored"])
def test_unknown_rule_suggests_ids_from_the_crawl(
    stopped_issue: tuple[Path, int], stored: bool
) -> None:
    file, _ = stopped_issue
    if not stored:
        with CrawlWriter(file, FakeClock()) as writer:
            writer.run(record_continue(read_recorded(file).config, _AT))

    with pytest.raises(OpenLinxError) as raised:
        read_affected_urls(file, "h1-missng", ())

    error = raised.value
    assert (error.code, error.exit_code) == ("rule_not_found", 4)
    assert error.diagnostic.details["suggestions"][0] == "h1-missing"
    assert "h1-missng" in error.diagnostic.message
    assert "linx rules list" in (error.diagnostic.hint or "")


def test_a_rule_missing_from_the_live_catalogue_explains_how_to_reproduce_it(
    stopped_issue: tuple[Path, int],
) -> None:
    file, url_id = stopped_issue
    assert query(file, "SELECT enabled FROM rules WHERE id = 'title-missing'") == [(1,)]
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
    with pytest.raises(OpenLinxError) as raised:
        read_affected_urls(file, "title-missing", ())

    diagnostic = raised.value.diagnostic
    assert (diagnostic.code, raised.value.exit_code) == ("rule_not_found", 4)
    message = diagnostic.message.casefold().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    running = r"while the crawl (?:runs|is running)"
    cannot_evaluate = (
        r"(?:this version|(?:(?:the|this) )?(?:installed|current) (?:version|catalogue|catalog))"
        r"(?: of \w+)? (?:cannot|can not|can't|is unable to) (?:compute|evaluate)"
        r" (?:the )?(?:recorded )?rule title-missing"
    )
    assert re.fullmatch(
        rf"(?:{running},? {cannot_evaluate}|{cannot_evaluate} (?:live|{running}))[.!]?",
        message,
    ), diagnostic.message
    hint = (diagnostic.hint or "").casefold()
    assert not re.search(r"\blinx\s+sql\b", hint), diagnostic.hint
    assert re.search(r"\bsqlite3\s+-readonly\b", hint), diagnostic.hint
    assert re.search(r"\b(?:this|(?:the )?selected) crawl\b", hint), diagnostic.hint
    assert re.search(r"\brules\b", hint), diagnostic.hint
    assert "reproduce_sql" in hint, diagnostic.hint

    [(statement,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", ("title-missing",))
    assert query(file, statement) == [(url_id, None)]


@pytest.mark.parametrize("reader", ["issues", "rule", "url", "evaluate"])
def test_live_readers_compile_only_recorded_enabled_rules(
    stopped_issue: tuple[Path, int],
    reader: str,
) -> None:
    file, url_id = stopped_issue
    incompatible = replace(
        TITLE_TOO_LONG, reproduce_sql="SELECT no_such_column AS url_id, NULL AS detail FROM pages"
    )
    unrecorded = replace(incompatible, id="later-rule")
    catalogue = (incompatible, unrecorded, TITLE_MISSING)
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.run(
            executing(update(rules).where(rules.c.id == "title-too-long").values(enabled=False))
        )
        writer.run(
            executing(
                update(rules)
                .where(rules.c.id == "title-missing")
                .values(reproduce_sql="SELECT no_such_column FROM pages")
            )
        )

    if reader == "evaluate":
        assert evaluate_rule(file, incompatible) == []
    elif reader == "issues":
        assert read_issues(file, catalogue) == [_ISSUE]
    elif reader == "rule":
        assert read_affected_urls(file, "title-too-long", catalogue) == []
        assert read_affected_urls(file, "title-too-long", ()) == []
        assert read_affected_urls(file, "title-missing", catalogue) == [
            AffectedUrl(url_id=url_id, detail=None)
        ]
    else:
        assert [(row.rule_id, row.url_id) for row in read_url_issues(file, url_id, catalogue)] == [
            ("title-missing", url_id)
        ]


@pytest.mark.parametrize(
    ("rule_id", "recorded_sql", "evaluable"),
    [
        *(
            pytest.param(rule_id, PREVIEW_NO_ROWS, False, id=rule_id)
            for rule_id in sorted(PREVIEW_RULE_IDS)
        ),
        pytest.param("h2-missing", PREVIEW_NO_ROWS + "\n", True, id="different-sql"),
        pytest.param("another-rule", PREVIEW_NO_ROWS, True, id="different-id"),
    ],
)
@pytest.mark.parametrize("reader", ["issues", "rule", "url", "evaluate", "final_pass"])
def test_only_an_exact_preview_placeholder_stays_empty(
    stopped_issue: tuple[Path, int], rule_id: str, recorded_sql: str, evaluable: bool, reader: str
) -> None:
    file, url_id = stopped_issue
    installed = replace(TITLE_MISSING, id=rule_id)

    def record_legacy_rule(connection: Connection) -> None:
        connection.exec_driver_sql("DELETE FROM affected_urls WHERE rule_id = ?", (rule_id,))
        connection.exec_driver_sql("DELETE FROM rules WHERE id = ?", (rule_id,))
        connection.exec_driver_sql(
            """INSERT INTO rules SELECT ?, category, issue_type, priority, applies_to, enabled,
               thresholds, description, why_it_matters, how_to_fix, ? FROM rules
               WHERE id = 'title-missing'""",
            (rule_id, recorded_sql),
        )

    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_continue(read_recorded(file).config, _AT))
        writer.run(record_legacy_rule)
        writer.flush()

    assert query(file, recorded_sql) == []
    assert query(file, installed.reproduce_sql) == [(url_id, None)]
    expected = [AffectedUrl(url_id=url_id, detail=None)] if evaluable else []
    if reader == "issues":
        issues = [replace(_ISSUE, rule_id=rule_id), _ISSUE] if evaluable else [_ISSUE]
        assert read_issues(file, (installed, TITLE_MISSING)) == issues
    elif reader == "rule":
        assert read_affected_urls(file, rule_id, (installed,)) == expected
    elif reader == "url":
        issues_for_url = (
            [UrlIssue(rule_id=rule_id, url_id=url_id, detail=None)] if evaluable else []
        )
        assert read_url_issues(file, url_id, (installed,)) == issues_for_url
    elif reader == "evaluate":
        assert evaluate_rule(file, installed) == expected
    else:
        _run_final_pass(file, installed)
        assert query(file, "SELECT url_id FROM affected_urls WHERE rule_id = ?", (rule_id,)) == [
            (row.url_id,) for row in expected
        ]


def _run_final_pass(file: Path, rule: Rule) -> None:
    async def materialise() -> None:
        with CrawlWriter(file, FakeClock()) as writer:
            await materialise_issues(writer, {rule.id: affected_urls_unit(rule)})

    asyncio.run(materialise())


@pytest.mark.parametrize("stored", [False, True], ids=["live", "stored"])
def test_issue_selects_compose_over_one_crawl_snapshot(
    stopped_issue: tuple[Path, int],
    stored: bool,
) -> None:
    file, url_id = stopped_issue
    with CrawlWriter(file, FakeClock()) as writer:
        if not stored:
            writer.run(record_continue(read_recorded(file).config, _AT))
            writer.flush()
        with reading(file) as connection:
            counts = issues_in(connection, _RULES).subquery()
            assert tuple(counts.c.keys()) == (
                "rule_id",
                "category",
                "issue_type",
                "priority",
                "affected_count",
            )
            assert (
                connection.execute(
                    select(counts.c.affected_count).where(counts.c.rule_id == "title-missing")
                ).scalar_one()
                == 1
            )
            _record_title(writer, url_id)
            writer.run(affected_urls_unit(TITLE_MISSING))
            writer.flush()
            found = affected_urls_in(connection, "title-missing", _RULES).subquery()
            assert tuple(found.c.keys()) == ("url_id", "detail")
            assert connection.execute(
                select(found.c.url_id, found.c.detail).where(found.c.url_id == url_id).limit(1)
            ).all() == [(url_id, None)]
    assert read_affected_urls(file, "title-missing", _RULES) == []
