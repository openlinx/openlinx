"""Verify URL Rules over stored display and encoded addresses."""

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.crawl.urls import NormalizedUrl
from openlinx.rules.registry import RULES
from openlinx.store.issues import read_affected_urls
from openlinx.store.pages import write_pages
from openlinx.store.records import FetchedUrl, Provenance
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.page_data import page_row, unprepared_page_row
from tests.support.workspace import TempWorkspace

_AT_LIMIT = "https://example.test/" + "a" * 94
_OVER_LIMIT = "https://example.test/" + "a" * 89 + "%C3%BC"
_ESCAPE_ONLY = "https://example.test/a%2Fb"
_UNDERSCORE_IN_QUERY = "https://example.test/shoes?utm_source=x"
_PARAMETERS = "https://example.test/shoes?page=2"
_NON_ASCII_PATH = "https://example.test/%C3%BCber"
_NON_ASCII_HOST = "https://xn--bcher-kva.test/"
_UPPERCASE = [
    "https://example.test/Shoes",
    "https://example.test/a%2F%3AFe%3f",
    "https://example.test/c?x=%2f%3A%25%2BC",
    "https://example.test/%D0%9A%D0%B0%D1%82/a%2F",
    "https://example.test/f?q=%F0%90%90%80",
    "https://example.test/%E1%B2%89",
]
_NON_ASCII = [
    "https://example.test/%D0%9A%D0%B0%D1%82/a%2F",
    "https://example.test/f?q=%F0%90%90%80",
    "https://example.test/%E1%B2%89",
    "https://example.test/%C7%85",
    "https://example.test/%E2%85%A0",
    _OVER_LIMIT,
    _NON_ASCII_PATH,
]


@pytest.fixture(scope="module")
def url_crawl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the shared Crawl once because each scenario opens it read-only."""
    addresses = [
        *_UPPERCASE,
        *_NON_ASCII[3:],
        "https://example.test/a%2F%3a%25",
        "https://example.test/b%25xA%2F",
        "https://example.test/c?x=%2F%3a%25",
        "https://example.test/a?",
        "https://example.test/red_shoes",
        _ESCAPE_ONLY,
        _UNDERSCORE_IN_QUERY,
        _PARAMETERS,
        _NON_ASCII_HOST,
        _AT_LIMIT,
        "https://example.test/NOT_FOUND?x=1",
    ]
    home = tmp_path_factory.mktemp("url-rules")
    root = home / "work"
    root.mkdir()
    file = create_any_crawl(TempWorkspace(home=home, root=root), seeds=addresses).path
    with CrawlWriter(file, FakeClock()) as writer:
        for address in addresses:
            url_id = writer.run(
                record_seed(NormalizedUrl(address), is_internal=True, in_scope=True)
            )
            parsed = not address.endswith("/NOT_FOUND?x=1")
            page = (
                page_row("<title>Shoes</title>", url=address)
                if parsed
                else unprepared_page_row(url=address, status_code=404)
            )
            writer.run(
                record_fetched(
                    FetchedUrl(
                        url_id=url_id,
                        provenance=Provenance(
                            crawl_depth=0, discovered_via="seed", found_on_url_id=None
                        ),
                        status_code=page.status_code,
                        content_type=page.content_type,
                        fetched_at=STARTED_AT,
                        response_time_ms=1,
                        parsed=parsed,
                        attempt_count=1,
                        redirect=None,
                        rows=(
                            HandlerRows(
                                write_pages,
                                (replace(page, url_id=url_id, crawl_timestamp=STARTED_AT),),
                            ),
                        ),
                    )
                )
            )
    return file


def _rule_results(
    url_crawl: Path, rule_id: str
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Read live Affected URLs and reproduce them in plain SQLite without linx functions."""
    rows = read_affected_urls(url_crawl, rule_id, RULES)
    with closing(sqlite3.connect(url_crawl.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        urls = dict(db.execute("SELECT id, url FROM urls"))
        [(sql,)] = db.execute("SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,)).fetchall()
        reproduced = db.execute(sql).fetchall()
    affected = {urls[row.url_id]: row.detail for row in rows}
    in_sqlite = {
        urls[url_id]: None if detail is None else json.loads(detail)
        for url_id, detail in reproduced
    }
    assert len(reproduced) == len(in_sqlite)
    return affected, in_sqlite


def _assert_affected_urls(url_crawl: Path, rule_id: str, expected: Mapping[str, object]) -> None:
    affected, in_sqlite = _rule_results(url_crawl, rule_id)
    assert affected == expected
    assert in_sqlite == expected


def _assert_unaffected_url(url_crawl: Path, rule_id: str, address: str) -> None:
    assert query(
        url_crawl,
        "SELECT urls.parsed FROM pages JOIN urls ON urls.id = pages.url_id WHERE urls.url = ?",
        (address,),
    ) == [(1,)]
    affected, in_sqlite = _rule_results(url_crawl, rule_id)
    assert address not in affected
    assert address not in in_sqlite


def test_uppercase_letters_in_the_path(url_crawl: Path) -> None:
    _assert_affected_urls(
        url_crawl, "url-uppercase", dict.fromkeys([*_UPPERCASE, "https://example.test/b%25xA%2F"])
    )


def test_uppercase_percent_escapes_are_ignored(url_crawl: Path) -> None:
    _assert_unaffected_url(url_crawl, "url-uppercase", _ESCAPE_ONLY)


def test_underscore_in_the_path(url_crawl: Path) -> None:
    _assert_affected_urls(url_crawl, "url-underscores", {"https://example.test/red_shoes": None})


def test_underscore_only_in_the_query(url_crawl: Path) -> None:
    _assert_unaffected_url(url_crawl, "url-underscores", _UNDERSCORE_IN_QUERY)


def test_parameters(url_crawl: Path) -> None:
    _assert_affected_urls(
        url_crawl,
        "url-parameters",
        dict.fromkeys(
            [
                "https://example.test/c?x=%2f%3A%25%2BC",
                "https://example.test/f?q=%F0%90%90%80",
                "https://example.test/c?x=%2F%3a%25",
                _UNDERSCORE_IN_QUERY,
                _PARAMETERS,
            ]
        ),
    )


def test_url_too_long(url_crawl: Path) -> None:
    _assert_affected_urls(url_crawl, "url-too-long", {_OVER_LIMIT: {"length": 116}})


def test_url_at_the_limit(url_crawl: Path) -> None:
    _assert_unaffected_url(url_crawl, "url-too-long", _AT_LIMIT)


def test_non_ascii_path(url_crawl: Path) -> None:
    assert query(
        url_crawl,
        "SELECT address FROM pages WHERE url_encoded_address = ?",
        (_NON_ASCII_PATH,),
    ) == [("https://example.test/über",)]
    _assert_affected_urls(url_crawl, "url-non-ascii", dict.fromkeys(_NON_ASCII))


def test_non_ascii_host_only(url_crawl: Path) -> None:
    assert query(
        url_crawl,
        "SELECT address FROM pages WHERE url_encoded_address = ?",
        (_NON_ASCII_HOST,),
    ) == [("https://bücher.test/",)]
    _assert_unaffected_url(url_crawl, "url-non-ascii", _NON_ASCII_HOST)


def test_url_length_uses_the_workspace_threshold(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        "[rules.url-too-long]\nmax_chars = 116\n[rules.url-parameters]\nenabled = false\n",
        encoding="utf-8",
    )
    path = "/" + "a" * 95
    hosts = fixture_hosts(Site({path: Page(body="<title>Shoes</title>")}), Site({}))
    result = crawl_result(f"http://site.test{path}?x=1", resolver=hosts.resolver)
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert query(file, "SELECT length(url_encoded_address), url_query FROM pages") == [(116, "x=1")]
    assert query(file, "SELECT enabled, thresholds FROM rules WHERE id = 'url-too-long'") == [
        (1, '{"max_chars":116}')
    ]
    assert query(file, "SELECT enabled FROM rules WHERE id = 'url-parameters'") == [(0,)]
    assert read_affected_urls(file, "url-too-long", RULES) == []
    assert read_affected_urls(file, "url-parameters", RULES) == []


def test_url_rule_catalogue_order(temp_workspace: TempWorkspace) -> None:
    result = run_cli("rules", "list", "--limit", "50")
    assert result.exit_code == 0, result.stderr
    assert [
        (item["id"], item["issue_type"], item["priority"], item["applies_to"], item["thresholds"])
        for item in result.json()["items"]
        if item["category"] == "urls"
    ] == [
        ("url-uppercase", "opportunity", "low", "internal_pages", {}),
        ("url-underscores", "opportunity", "low", "internal_pages", {}),
        ("url-parameters", "opportunity", "low", "internal_pages", {}),
        (
            "url-too-long",
            "opportunity",
            "low",
            "internal_pages",
            {"max_chars": {"value": 115, "default": 115, "unit": "characters"}},
        ),
        ("url-non-ascii", "opportunity", "low", "internal_pages", {}),
    ]
