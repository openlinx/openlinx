"""Verify the Query Service's Issue order and consistent Crawl reads."""

import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from shutil import copyfile
from threading import Event

import orjson
import pytest
from sqlalchemy import Connection, Engine, Select, event, update

from openlinx.crawl.urls import NormalizedUrl
from openlinx.output.diagnostics import OpenLinxError
from openlinx.rules.titles import TITLE_MISSING
from openlinx.services.query import QueryRequest, issue_list
from openlinx.store.crawls import record_state
from openlinx.store.issues import affected_urls_unit
from openlinx.store.pages import write_pages
from openlinx.store.records import FetchedUrl, JournalSetting, Provenance, RuleRow
from openlinx.store.rows import HandlerRows
from openlinx.store.schema import rules
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import PROCESS_TIMEOUT
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, query, sha256_of
from tests.support.page_data import page_row
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


def test_order(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace)
    result = issue_list(QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home))

    assert (result.total, result.next_cursor) == (7, None)
    assert [
        (item["rule_id"], item["issue_type"], item["priority"], item["affected_count"])
        for item in result.items
    ] == [
        ("rule-d", "issue", "high", 9),
        ("rule-e", "issue", "high", 9),
        ("rule-c", "issue", "high", 1),
        ("rule-f", "issue", "medium", 10),
        ("rule-b", "issue", "low", 3),
        ("rule-a", "warning", "high", 50),
        ("rule-g", "opportunity", "high", 1),
    ]


def test_issue_list_refuses_a_completed_crawl_from_before_rules(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="<p>Next</p>")})
    )
    file = crawl_result(server.url("/")).crawl_file
    # Emulate the pre-release schema, which used the same version and had no Rule objects.
    with closing(sqlite3.connect(file)) as connection:
        connection.execute("DROP VIEW issues")
        connection.execute("DROP TABLE affected_urls")
        connection.execute("DROP TABLE rules")
    assert query(file, "PRAGMA user_version") == [(1,)]
    assert query(file, "SELECT state, (SELECT count(*) FROM pages) FROM crawl") == [
        ("completed", 2)
    ]
    before = sha256_of(file)

    with pytest.raises(OpenLinxError) as caught:
        issue_list(QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file)))

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "crawl_file_invalid",
        6,
        {"file": str(file)},
    )
    assert sha256_of(file) == before


def test_issue_list_detects_replacement_after_crawl_selection(
    temp_workspace: TempWorkspace,
) -> None:
    file = crawl_store(temp_workspace)
    replacement = file.with_suffix(".replacement")
    copyfile(file, replacement)

    def replace_after_metadata_read(_engine: Engine) -> None:
        if replacement.exists():
            replacement.replace(file)

    # Selection has closed its read. Even a byte-for-byte copy has another file identity.
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))
    event.listen(Engine, "engine_disposed", replace_after_metadata_read)
    try:
        with pytest.raises(OpenLinxError) as caught:
            issue_list(request)
    finally:
        event.remove(Engine, "engine_disposed", replace_after_metadata_read)

    assert not replacement.exists()
    assert caught.value.code == "crawl_not_writable"
    assert caught.value.diagnostic.details == {"file": str(file)}


def test_issue_list_keeps_the_recorded_description_in_the_same_snapshot(
    temp_workspace: TempWorkspace,
) -> None:
    file = crawl_store(temp_workspace)
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    committed = False
    with CrawlWriter(file, FakeClock()) as writer:

        def commit_before_rule_read(
            connection: Connection,
            clause: object,
            multiparams: object,
            params: object,
            execution_options: object,
        ) -> None:
            nonlocal committed
            if (
                committed
                or not isinstance(clause, Select)
                or not any(source.is_derived_from(rules) for source in clause.get_final_froms())
            ):
                return
            committed = True
            writer.run(
                executing(
                    update(rules)
                    .where(rules.c.id == "rule-d")
                    .values(description="New recorded guidance for rule-d.")
                )
            )
            writer.flush()

        # On a completed Crawl the reader checks state before consulting the Rule catalogue.
        # Commit between those reads so the description must come from the existing snapshot.
        event.listen(Engine, "before_execute", commit_before_rule_read)
        try:
            result = issue_list(request)
        finally:
            event.remove(Engine, "before_execute", commit_before_rule_read)

    assert committed
    assert orjson.loads(orjson.dumps(result.items[0])) == {
        "rule_id": "rule-d",
        "category": "response_codes",
        "issue_type": "issue",
        "priority": "high",
        "affected_count": 9,
        "description": "Recorded guidance for rule-d.",
    }
    assert issue_list(request).items[0]["description"] == "New recorded guidance for rule-d."


def _reader_blocks_commit(file: Path) -> bool:
    # With no other write in progress, an exclusive lock fails only in DELETE with a live reader.
    # Make this observation before starting the Writer commit so the test never waits for itself.
    with closing(sqlite3.connect(file, timeout=0)) as probe:
        try:
            probe.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as error:
            if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                return True
            raise
        probe.rollback()
        return False


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_issue_list_uses_one_snapshot_across_the_final_pass(
    temp_workspace: TempWorkspace, journal_mode: JournalSetting
) -> None:
    current = TITLE_MISSING
    historical = replace(current, id="later-rule")
    recorded = RuleRow(
        id=current.id,
        category=current.category,
        issue_type=current.issue_type,
        priority=current.priority,
        applies_to=current.applies_to,
        enabled=True,
        thresholds={},
        description=current.description,
        why_it_matters=current.why_it_matters,
        how_to_fix=current.how_to_fix,
        reproduce_sql=current.reproduce_sql,
    )
    file = create_any_crawl(
        temp_workspace,
        rules=(recorded, replace(recorded, id=historical.id)),
        journal_setting=journal_mode,
    ).path
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    url = NormalizedUrl("https://example.com/")
    committing = Event()
    pending: Future[None] | None = None
    blocks_commit = False

    with CrawlWriter(file, FakeClock()) as writer, ThreadPoolExecutor(max_workers=1) as executor:
        url_id = writer.run(record_seed(url, is_internal=True, in_scope=True))
        writer.flush()
        assert query(file, "SELECT state, journal_mode FROM crawl") == [("running", journal_mode)]
        assert issue_list(request).items == []

        def finish_crawl(connection: Connection) -> None:
            record_fetched(
                FetchedUrl(
                    url_id=url_id,
                    provenance=Provenance(
                        crawl_depth=0, discovered_via="seed", found_on_url_id=None
                    ),
                    status_code=200,
                    content_type="text/html",
                    fetched_at=STARTED_AT + timedelta(seconds=1),
                    response_time_ms=10,
                    parsed=True,
                    attempt_count=1,
                    redirect=None,
                    rows=(HandlerRows(write_pages, (page_row("<p>Seed</p>", url=str(url)),)),),
                )
            )(connection)
            for rule in (current, historical):
                affected_urls_unit(rule)(connection)
            record_state("completed", STARTED_AT + timedelta(seconds=2))(connection)

        def commit() -> None:
            writer.run(finish_crawl)
            writer.flush()

        def starting_commit(connection: Connection) -> None:
            committing.set()

        def finish_after_live_choice(
            connection: Connection,
            clause: object,
            multiparams: object,
            params: object,
            execution_options: object,
        ) -> None:
            nonlocal pending, blocks_commit
            if (
                pending is not None
                or not isinstance(clause, Select)
                or not any(source.is_derived_from(rules) for source in clause.get_final_froms())
            ):
                return
            blocks_commit = _reader_blocks_commit(file)
            pending = executor.submit(commit)
            if blocks_commit:
                assert committing.wait(PROCESS_TIMEOUT)
                assert not pending.done()
            else:
                pending.result(timeout=PROCESS_TIMEOUT)

        # Finish after the reader has picked live Issues but before it reads any Rules.
        event.listen(Engine, "before_execute", finish_after_live_choice)
        event.listen(Engine, "commit", starting_commit)
        try:
            observed = issue_list(request)
            assert pending is not None
            pending.result(timeout=PROCESS_TIMEOUT)
        finally:
            event.remove(Engine, "commit", starting_commit)
            event.remove(Engine, "before_execute", finish_after_live_choice)

    assert observed.items == []
    assert blocks_commit == (journal_mode == "delete")
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert [(item["rule_id"], item["affected_count"]) for item in issue_list(request).items] == [
        ("later-rule", 1),
        ("title-missing", 1),
    ]
