"""Read recorded Rule metadata and Affected URLs through the Query Service."""

import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import Connection, Engine, event

from openlinx.crawl.urls import NormalizedUrl
from openlinx.output.diagnostics import OpenLinxError
from openlinx.rules.response_codes import INTERNAL_4XX
from openlinx.rules.settings import RulesSettings
from openlinx.services import query
from openlinx.services.rules import rule_rows
from openlinx.store.crawls import record_state
from openlinx.store.issues import affected_urls_unit
from openlinx.store.records import FetchedUrl, JournalSetting, Provenance, RuleRow
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.crawls import STARTED_AT, create_any_crawl
from tests.support.workspace import TempWorkspace


def test_a_rule_that_did_not_fire(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, pages={"https://example.com/a": "<h1>Welcome</h1>"})
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    found = query.issue_detail(request, "h1-missing")

    assert (found.total, found.items, found.next_cursor) == (0, [], None)
    assert found.header["rule"]["rule_id"] == "h1-missing"
    assert found.header["rule"]["category"] == "headings"


@pytest.mark.parametrize(
    "max_hops", [pytest.param(3, id="three"), pytest.param(10**700 + 7, id="wide-integer")]
)
def test_thresholds_recorded_for_the_crawl(temp_workspace: TempWorkspace, max_hops: int) -> None:
    snapshot = RuleRow(
        id="redirect-chain",
        category="response_codes",
        issue_type="warning",
        priority="medium",
        applies_to="internal_urls",
        enabled=True,
        thresholds={"max_hops": max_hops},
        description="An Internal URL has a Redirect Chain longer than max_hops.",
        why_it_matters="Each redirect adds a request.",
        how_to_fix="Link directly to the destination.",
        reproduce_sql="SELECT id AS url_id, NULL AS detail FROM urls WHERE 0",
    )
    file = create_any_crawl(temp_workspace, rules=[snapshot]).path
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=1)))
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    # The reader can run under a lower decimal conversion limit than the Crawl did.
    previous_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(sys.int_info.str_digits_check_threshold)
    try:
        found = query.issue_detail(request, "redirect-chain")
    finally:
        sys.set_int_max_str_digits(previous_limit)

    thresholds = found.header["rule"]["thresholds"]
    assert thresholds == {"max_hops": max_hops}
    assert type(thresholds["max_hops"]) is int


def test_guidance_of_the_rule(temp_workspace: TempWorkspace) -> None:
    installed = next(
        row for row in rule_rows(RulesSettings().model_dump()) if row.id == "title-too-long"
    )
    recorded = replace(
        installed,
        description="The first title exceeds this Crawl's character limit.",
        why_it_matters="Search results can truncate a long title.",
        how_to_fix="Keep the topic in the first 70 characters of the title.",
        thresholds={"max_chars": 70},
    )
    file = create_any_crawl(temp_workspace, rules=[recorded]).path
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=1)))
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    found = query.issue_detail(request, "title-too-long")

    rule = found.header["rule"]
    assert (rule["description"], rule["why_it_matters"], rule["how_to_fix"]) == (
        "The first title exceeds this Crawl's character limit.",
        "Search results can truncate a long title.",
        "Keep the topic in the first 70 characters of the title.",
    )


def test_the_reproducing_query_of_the_rule(temp_workspace: TempWorkspace) -> None:
    installed = next(
        row for row in rule_rows(RulesSettings().model_dump()) if row.id == "title-missing"
    )
    recorded_sql = "SELECT url_id, NULL AS detail\nFROM pages\nWHERE title_count = 0"
    recorded = replace(installed, reproduce_sql=recorded_sql)
    file = create_any_crawl(temp_workspace, rules=[recorded]).path
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    found = query.issue_detail(request, "title-missing")

    assert found.header["rule"]["reproduce_sql"] == recorded_sql


def test_pages_stored_affected_urls_in_url_order(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace,
        pages={
            "https://example.com/z": "<h1>Welcome</h1>",
            "https://example.com/a": "<h1>Welcome</h1>",
            "https://example.com/m": "<h1>Welcome</h1>",
        },
    )
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    first = query.issue_detail(request, "title-missing", limit=2)
    assert (first.total, first.items) == (
        3,
        [
            {"url": "https://example.com/a", "detail": None},
            {"url": "https://example.com/m", "detail": None},
        ],
    )
    assert first.next_cursor is not None

    last = query.issue_detail(
        request, "title-missing", limit=1, cursor=first.next_cursor, fields="url"
    )
    count_only = query.issue_detail(request, "title-missing", limit=0, cursor=first.next_cursor)

    assert (last.total, last.items, last.next_cursor) == (
        3,
        [{"url": "https://example.com/z"}],
        None,
    )
    assert (count_only.total, count_only.items, count_only.next_cursor) == (3, [], None)
    assert count_only.header["rule"]["rule_id"] == "title-missing"


def test_live_pages_use_current_rows_and_continue_after_the_last_url(
    temp_workspace: TempWorkspace,
) -> None:
    seeds = ["https://example.com/z", "https://example.com/b", "https://example.com/a"]
    file = create_any_crawl(temp_workspace, crawl_mode="list", seeds=seeds).path
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    def fetch(url_id: int, status_code: int, seconds: int) -> FetchedUrl:
        return FetchedUrl(
            url_id=url_id,
            provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
            status_code=status_code,
            content_type="text/plain",
            fetched_at=STARTED_AT + timedelta(seconds=seconds),
            response_time_ms=10,
            parsed=False,
            attempt_count=1,
            redirect=None,
        )

    with CrawlWriter(file, FakeClock()) as writer:
        last, middle, earlier = [
            writer.run(record_seed(NormalizedUrl(url), is_internal=True, in_scope=True))
            for url in seeds
        ]
        writer.run(record_fetched(fetch(last, 404, 1)))
        # Leave the earlier pass's result in place while new responses reach the running Crawl.
        writer.run(affected_urls_unit(INTERNAL_4XX))
        writer.run(record_fetched(fetch(middle, 410, 2)))
        writer.flush()

        first = query.issue_detail(request, "internal-4xx", limit=1, fields="detail")
        assert (first.total, first.items) == (2, [{"detail": {"status_code": 410}}])
        assert first.next_cursor is not None

        writer.run(record_fetched(fetch(earlier, 403, 3)))
        writer.flush()
        second = query.issue_detail(request, "internal-4xx", limit=1, cursor=first.next_cursor)

    assert (second.total, second.items, second.next_cursor) == (
        3,
        [{"url": "https://example.com/z", "detail": {"status_code": 404}}],
        None,
    )


def test_detail_cursor_is_bound_to_the_crawl_and_rule(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        pages={"https://example.com/a": "<h1>A</h1>", "https://example.com/b": "<h1>B</h1>"},
    )
    other = create_any_crawl(temp_workspace).path
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))
    first = query.issue_detail(request, "title-missing", limit=1)
    assert first.next_cursor is not None

    with pytest.raises(OpenLinxError) as other_rule:
        query.issue_detail(request, "h1-missing", cursor=first.next_cursor)
    assert other_rule.value.code == "invalid_cursor"

    with pytest.raises(OpenLinxError) as other_crawl:
        query.issue_detail(
            replace(request, crawl=str(other)), "title-missing", cursor=first.next_cursor
        )
    assert other_crawl.value.code == "invalid_cursor"


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_rule_header_and_affected_urls_share_one_snapshot(
    temp_workspace: TempWorkspace, journal_mode: JournalSetting
) -> None:
    file = crawl_store(
        temp_workspace,
        example_issues=(("rule-a", "issue", "high", 3),),
        journal_setting=journal_mode,
    )
    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    commit_blocked: bool | None = None
    with closing(sqlite3.connect(file, timeout=0)) as writer:

        def publish_updated_results(
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

        # Try the Writer commit when the reader reaches Affected URLs. In rollback mode the
        # read transaction holds the Writer until the service has collected its response.
        event.listen(Engine, "before_cursor_execute", publish_updated_results)
        try:
            first = query.issue_detail(request, "rule-a", limit=1)
        finally:
            event.remove(Engine, "before_cursor_execute", publish_updated_results)
        writer.commit()

    assert commit_blocked is (journal_mode == "delete")
    assert (first.header["rule"]["description"], first.total, first.items) == (
        "Recorded guidance for rule-a.",
        3,
        [{"url": "https://example.com/rule-a/0", "detail": None}],
    )
    fresh = query.issue_detail(request, "rule-a", limit=1)
    assert (fresh.header["rule"]["description"], fresh.total, fresh.items) == (
        "Later guidance.",
        2,
        [{"url": "https://example.com/rule-a/1", "detail": None}],
    )
