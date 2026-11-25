"""Verify the Query Service's Rule header and Affected URL pages."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import Connection, Engine, event

from openlinx.crawl.urls import NormalizedUrl
from openlinx.json_numbers import encode_json
from openlinx.output.diagnostics import OpenLinxError
from openlinx.rules.settings import RulesSettings
from openlinx.services.query import QueryRequest, issue_detail
from openlinx.services.rules import rule_rows
from openlinx.store.crawls import record_state
from openlinx.store.records import FetchedUrl, JournalSetting, Provenance
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.workspace import TempWorkspace


def test_a_rule_that_did_not_fire(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, pages={"https://example.com/a": "<h1>Welcome</h1>"})
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    found = issue_detail(request, "h1-missing")

    assert (found.total, found.items, found.next_cursor) == (0, [], None)
    assert json.loads(encode_json(found.header))["rule"]["rule_id"] == "h1-missing"


def test_thresholds_recorded_for_the_crawl(temp_workspace: TempWorkspace) -> None:
    settings = RulesSettings.model_validate({"title-too-long": {"max_chars": 70}})
    file = crawl_store(
        temp_workspace,
        pages={"https://example.com/a": "<title>Welcome</title>"},
        rule_settings=settings.model_dump(),
    )
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = issue_detail(request, "title-too-long")

    thresholds = result.header["rule"]["thresholds"]
    assert thresholds == {"max_chars": 70}
    assert type(thresholds["max_chars"]) is int


def test_guidance_of_the_rule(temp_workspace: TempWorkspace) -> None:
    installed = next(
        row for row in rule_rows(RulesSettings().model_dump()) if row.id == "title-too-long"
    )
    historical = replace(
        installed,
        description="The first title exceeds this Crawl's character limit.",
        why_it_matters="Search results can truncate a long title.",
        how_to_fix="Keep the topic in the first 70 characters of the title.",
        thresholds={"max_chars": 70},
    )
    assert historical.how_to_fix != installed.how_to_fix
    file = create_any_crawl(temp_workspace, rules=(historical,)).path
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=1)))
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    result = issue_detail(request, "title-too-long")

    header = result.header["rule"]
    assert (header["description"], header["why_it_matters"], header["how_to_fix"]) == (
        "The first title exceeds this Crawl's character limit.",
        "Search results can truncate a long title.",
        "Keep the topic in the first 70 characters of the title.",
    )


def test_the_reproducing_query_of_the_rule(temp_workspace: TempWorkspace) -> None:
    recorded_sql = "SELECT url_id, NULL AS detail\nFROM pages\nWHERE title_count = 0"
    installed = next(
        row for row in rule_rows(RulesSettings().model_dump()) if row.id == "title-missing"
    )
    assert recorded_sql != installed.reproduce_sql
    historical = replace(installed, reproduce_sql=recorded_sql)
    file = create_any_crawl(temp_workspace, rules=(historical,)).path
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    result = issue_detail(request, "title-missing")

    assert result.header["rule"]["reproduce_sql"] == recorded_sql


def test_detail_of_an_affected_url(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(temp_workspace, pages={"https://example.com/gone": None})
    assert query(
        file,
        "SELECT crawl.state, urls.status_code FROM crawl CROSS JOIN urls "
        "WHERE urls.url = 'https://example.com/gone'",
    ) == [("completed", 404)]
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    result = issue_detail(request, "internal-4xx")

    assert (result.total, result.items, result.next_cursor) == (
        1,
        [{"url": "https://example.com/gone", "detail": {"status_code": 404}}],
        None,
    )


def test_detail_pages_stored_urls_in_url_order(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/z": "<h1>Welcome</h1>",
            "https://example.com/a": "<h1>Welcome</h1>",
            "https://example.com/m": "<h1>Welcome</h1>",
        },
    )
    assert query(file, "SELECT url FROM urls WHERE url != 'https://example.com/' ORDER BY id") == [
        ("https://example.com/z",),
        ("https://example.com/a",),
        ("https://example.com/m",),
    ]
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    first = issue_detail(request, "title-missing", limit=2)
    assert first.next_cursor
    second = issue_detail(request, "title-missing", limit=2, cursor=first.next_cursor)

    assert (first.total, first.items) == (
        3,
        [
            {"url": "https://example.com/a", "detail": None},
            {"url": "https://example.com/m", "detail": None},
        ],
    )
    assert (second.total, second.items, second.next_cursor) == (
        3,
        [{"url": "https://example.com/z", "detail": None}],
        None,
    )


def test_a_live_page_resumes_after_the_url_even_when_an_earlier_url_finishes(
    temp_workspace: TempWorkspace,
) -> None:
    seeds = ("https://example.com/z", "https://example.com/b", "https://example.com/a")
    file = create_any_crawl(temp_workspace, crawl_mode="list", seeds=list(seeds)).path
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    def finish(url_id: int, seconds: int) -> FetchedUrl:
        return FetchedUrl(
            url_id=url_id,
            provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
            status_code=404,
            content_type="text/plain",
            fetched_at=STARTED_AT + timedelta(seconds=seconds),
            response_time_ms=10,
            parsed=False,
            attempt_count=1,
            redirect=None,
        )

    with CrawlWriter(file, FakeClock()) as writer:
        z, b, a = [
            writer.run(record_seed(NormalizedUrl(url), is_internal=True, in_scope=True))
            for url in seeds
        ]
        writer.run(record_fetched(finish(z, 1)))
        writer.run(record_fetched(finish(b, 2)))
        writer.flush()
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert query(file, "SELECT count(*) FROM affected_urls") == [(0,)]

        first = issue_detail(request, "internal-4xx", limit=1, fields="url")
        assert (first.total, first.items) == (2, [{"url": "https://example.com/b"}])
        assert first.next_cursor

        writer.run(record_fetched(finish(a, 3)))
        writer.flush()
        second = issue_detail(
            request, "internal-4xx", limit=1, cursor=first.next_cursor, fields="url"
        )

    assert (second.total, second.items, second.next_cursor) == (
        3,
        [{"url": "https://example.com/z"}],
        None,
    )


def test_a_detail_cursor_cannot_be_used_for_another_rule(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace,
        example_issues=(("rule-a", "issue", "high", 3), ("rule-b", "issue", "high", 1)),
    )
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    first = issue_detail(request, "rule-a", limit=2)

    assert first.next_cursor
    assert issue_detail(request, "rule-b").items == [
        {"url": "https://example.com/rule-b/0", "detail": None}
    ]
    with pytest.raises(OpenLinxError) as raised:
        issue_detail(request, "rule-b", limit=2, cursor=first.next_cursor)
    assert raised.value.code == "invalid_cursor"


def test_a_detail_cursor_cannot_be_used_for_another_crawl(temp_workspace: TempWorkspace) -> None:
    source_file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/a": "<h1>First</h1>",
            "https://example.com/b": "<h1>Second</h1>",
        },
    )
    other_file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/a": "<h1>First</h1>",
            "https://example.com/z": "<h1>Last</h1>",
        },
    )
    ((source_id,),) = query(source_file, "SELECT id FROM crawl")
    ((other_id,),) = query(other_file, "SELECT id FROM crawl")
    assert source_id != other_id
    source = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=source_id)
    other = replace(source, crawl=other_id)

    first = issue_detail(source, "title-missing", limit=1)
    other_first = issue_detail(other, "title-missing", limit=1)
    for page in (first, other_first):
        assert (page.total, page.items) == (
            2,
            [{"url": "https://example.com/a", "detail": None}],
        )
        assert page.next_cursor
    original_second = issue_detail(source, "title-missing", limit=1, cursor=first.next_cursor)
    other_second = issue_detail(other, "title-missing", limit=1, cursor=other_first.next_cursor)
    assert (original_second.items, original_second.next_cursor) == (
        [{"url": "https://example.com/b", "detail": None}],
        None,
    )
    assert (other_second.items, other_second.next_cursor) == (
        [{"url": "https://example.com/z", "detail": None}],
        None,
    )

    with pytest.raises(OpenLinxError) as raised:
        issue_detail(other, "title-missing", limit=1, cursor=first.next_cursor)
    assert raised.value.code == "invalid_cursor"


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_the_rule_header_and_affected_urls_share_a_snapshot(
    temp_workspace: TempWorkspace, journal_mode: JournalSetting
) -> None:
    file = crawl_store(
        temp_workspace,
        example_issues=(("rule-a", "issue", "high", 3),),
        journal_setting=journal_mode,
    )
    assert query(file, "PRAGMA journal_mode") == [(journal_mode,)]
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    commit_blocked: bool | None = None
    with closing(sqlite3.connect(file, timeout=0)) as writer:

        def change_recorded_results(
            connection: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            nonlocal commit_blocked
            if commit_blocked is not None or "affected_urls" not in statement:
                return
            writer.execute("UPDATE rules SET description = 'Later guidance.' WHERE id = 'rule-a'")
            writer.execute(
                "DELETE FROM affected_urls WHERE rule_id = 'rule-a' AND url_id = "
                "(SELECT id FROM urls WHERE url = 'https://example.com/rule-a/0')"
            )
            try:
                writer.commit()
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                    raise
                commit_blocked = True
            else:
                commit_blocked = False

        # The reader has checked the Rule and Crawl State when it reaches Affected URLs.
        # DELETE refuses its commit until the response releases the read snapshot.
        event.listen(Engine, "before_cursor_execute", change_recorded_results)
        try:
            first = issue_detail(request, "rule-a", limit=1)
        finally:
            event.remove(Engine, "before_cursor_execute", change_recorded_results)
        writer.commit()

    assert commit_blocked == (journal_mode == "delete")
    assert (first.header["rule"]["description"], first.total, first.items) == (
        "Recorded guidance for rule-a.",
        3,
        [{"url": "https://example.com/rule-a/0", "detail": None}],
    )
    fresh = issue_detail(request, "rule-a", limit=1)
    assert (fresh.header["rule"]["description"], fresh.total, fresh.items) == (
        "Later guidance.",
        2,
        [{"url": "https://example.com/rule-a/1", "detail": None}],
    )


@pytest.mark.parametrize(
    "max_chars",
    [
        pytest.param(2**64 + 1, id="beyond-uint64"),
        pytest.param(10**4300 - 1, id="4300-digits"),
    ],
)
def test_detail_preserves_large_recorded_integers(
    temp_workspace: TempWorkspace, max_chars: int
) -> None:
    settings = RulesSettings.model_validate({"title-too-long": {"max_chars": max_chars}})
    file = create_any_crawl(temp_workspace, rules=rule_rows(settings.model_dump())).path
    assert query(file, "SELECT thresholds FROM rules WHERE id = 'title-too-long'") == [
        (f'{{"max_chars":{max_chars}}}',)
    ]
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = issue_detail(request, "title-too-long")

    recorded = result.header["rule"]["thresholds"]["max_chars"]
    assert type(recorded) is int
    assert recorded == max_chars
