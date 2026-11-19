"""Read stored Issue counts and verify per-Rule replacement on Writer replay."""

import json
from decimal import Decimal
from operator import itemgetter
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection

from openlinx.rules.titles import TITLE_MISSING
from openlinx.store.issues import affected_urls_unit
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now

RULE_PAGES = Site(
    {
        "/rules/": Page(body='<title>Rules</title><a href="/rules/untitled">Untitled</a>'),
        "/rules/untitled": Page(body="<p>Missing title</p>"),
    }
)


@pytest.fixture
def issue_crawl(temp_workspace: TempWorkspace, fixture_site: StartSite) -> tuple[Path, str]:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/second">Second</a><a href="/titled">Titled</a>'),
                "/second": Page(body="<p>No title</p>"),
                "/titled": Page(body="<title>Present</title>"),
            }
        )
    )
    return crawled(server.url("/")), server.url("/")


def stored_missing_titles(file: Path) -> list[tuple[str, None]]:
    return query(
        file,
        "SELECT u.url, a.detail FROM affected_urls AS a JOIN urls AS u ON a.url_id = u.id "
        "WHERE a.rule_id = 'title-missing' ORDER BY u.url",
    )


def missing_title_issue(file: Path) -> list[tuple[str, str, str, int]]:
    return query(
        file,
        "SELECT category, issue_type, priority, affected_count FROM issues "
        "WHERE rule_id = 'title-missing'",
    )


def test_issue_row_counts_its_affected_urls(issue_crawl: tuple[Path, str]) -> None:
    file, root = issue_crawl
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert stored_missing_titles(file) == [(root, None), (root + "second", None)]
    assert missing_title_issue(file) == [("titles", "issue", "high", 2)]


def test_replay_replaces_only_the_affected_urls_of_one_rule(
    issue_crawl: tuple[Path, str],
) -> None:
    file, root = issue_crawl

    def seed_previous_result(connection: Connection) -> None:
        connection.exec_driver_sql("DELETE FROM affected_urls WHERE rule_id = 'title-missing'")
        for rule in ("title-missing", "internal-4xx"):
            connection.exec_driver_sql(
                "INSERT INTO affected_urls(rule_id, url_id, detail) "
                "SELECT ?, id, NULL FROM urls WHERE url = ?",
                (rule, root + "titled"),
            )

    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(seed_previous_result)
        writer.flush()
        assert missing_title_issue(file) == [("titles", "issue", "high", 1)]

        unit = affected_urls_unit(TITLE_MISSING)
        writer.run(unit)
        writer.run(unit)
        assert stored_missing_titles(file) == [(root + "titled", None)]
        replay_now(writer)

    assert stored_missing_titles(file) == [(root, None), (root + "second", None)]
    assert missing_title_issue(file) == [("titles", "issue", "high", 2)]
    assert query(
        file,
        "SELECT url FROM urls JOIN affected_urls ON url_id = id "
        "WHERE rule_id = 'internal-4xx' AND url = ?",
        (root + "titled",),
    ) == [(root + "titled",)]


def _json_number(token: str) -> tuple[Decimal]:
    # A tuple keeps JSON numbers distinct from booleans. JSON arrays decode as lists.
    return (Decimal(token),)


def _decoded_details(rows: list[tuple[Any, ...]]) -> list[tuple[int, object]]:
    decoded = []
    for url_id, detail in sorted(rows, key=itemgetter(0)):
        value = None
        if detail is not None:
            value = json.loads(detail, parse_int=_json_number, parse_float=_json_number)
            assert isinstance(value, dict), f"expected a JSON object in detail, got {detail!r}"
        decoded.append((url_id, value))
    return decoded


@pytest.mark.usefixtures("temp_workspace")
def test_a_rule_s_query_returns_its_stored_affected_urls(fixture_site: StartSite) -> None:
    server = fixture_site(RULE_PAGES)
    file = crawled(server.url("/rules/"))

    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert (server.url("/rules/untitled"), None) in stored_missing_titles(file)
    rules = dict(query(file, "SELECT id, reproduce_sql FROM rules WHERE enabled = 1"))
    assert "title-missing" in rules
    for rule_id, sql in rules.items():
        stored = query(
            file, "SELECT url_id, detail FROM affected_urls WHERE rule_id = ?", (rule_id,)
        )
        assert _decoded_details(query(file, sql)) == _decoded_details(stored), rule_id
