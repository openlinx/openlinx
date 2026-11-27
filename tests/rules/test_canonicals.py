"""Verify canonical Rules over Pages in a real crawl store."""

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Connection

from openlinx.crawl.engine.hooks import UrlResult, handler
from openlinx.crawl.urls import NormalizedUrl
from openlinx.rules.registry import RULES
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import evaluate_rule
from openlinx.store.page_records import PageRow
from openlinx.store.pages import write_pages
from openlinx.store.records import AffectedUrl, FetchedUrl, Provenance, Redirect
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.page_data import page_row, unprepared_page_row
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(
    "target_status",
    [pytest.param(301, id="http-redirect"), pytest.param(200, id="http-refresh")],
)
def test_canonical_to_a_redirect(temp_workspace: TempWorkspace, target_status: int) -> None:
    source = "https://example.test/a"
    target = "https://example.test/b"
    crawl = create_any_crawl(
        temp_workspace,
        seeds=[source, target],
        command_argv=["linx", "crawl", source, target],
        scope={
            "mode": "host",
            "hosts": ["example.test"],
            "folder": None,
            "include": [],
            "exclude": [],
        },
    )
    source_page = page_row('<link rel="canonical" href="https://example.test/b">', url=source)
    if target_status == 301:
        target_page = unprepared_page_row(url=target, status_code=301)
        redirect = Redirect(location=None, target=None, max_redirects=5)
    else:
        target_page = page_row(
            "<title>Redirect</title>", headers=(("Refresh", "0; url=/c"),), url=target
        )
        redirect = None
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        source_id = _record_seed_page(writer, source, source_page)
        target_id = _record_seed_page(writer, target, target_page, redirect=redirect)

    assert query(
        crawl.path,
        "SELECT indexability, indexability_status FROM pages WHERE url_id = ?",
        (target_id,),
    ) == [("non_indexable", "redirected")]
    matching = [rule for rule in RULES if rule.id == "canonical-to-non-indexable"]
    assert len(matching) == 1, "The catalogue must register canonical-to-non-indexable once"
    [rule] = matching
    assert (rule.category, rule.issue_type, rule.priority, rule.applies_to, rule.thresholds) == (
        "canonicals",
        "issue",
        "high",
        "internal_pages",
        (),
    )
    assert evaluate_rule(crawl.path, rule) == [
        AffectedUrl(
            url_id=source_id,
            detail={"canonical_url": "https://example.test/b", "target_reason": "redirected"},
        )
    ]


@pytest.mark.parametrize(
    ("target_html", "target_headers"),
    [
        pytest.param('<meta name="robots" content="noindex">', (), id="meta-robots"),
        pytest.param("<title>Target</title>", (("X-Robots-Tag", "noindex"),), id="x-robots-tag"),
    ],
)
def test_canonical_to_a_noindex_page(
    temp_workspace: TempWorkspace,
    target_html: str,
    target_headers: tuple[tuple[str, str], ...],
) -> None:
    source = "https://example.test/a"
    target = "https://example.test/b"
    crawl = create_any_crawl(
        temp_workspace,
        seeds=[source, target],
        command_argv=["linx", "crawl", source, target],
        scope={
            "mode": "host",
            "hosts": ["example.test"],
            "folder": None,
            "include": [],
            "exclude": [],
        },
    )
    source_page = page_row('<link rel="canonical" href="https://example.test/b">', url=source)
    # This Page would also match as its own target if the SQL admitted self-canonicals.
    target_page = page_row(
        f'<link rel="canonical" href="https://example.test/b">{target_html}',
        headers=target_headers,
        url=target,
    )
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        source_id = _record_seed_page(writer, source, source_page)
        target_id = _record_seed_page(writer, target, target_page)

    assert query(
        crawl.path,
        "SELECT status_code, indexability, indexability_status, canonical_url "
        "FROM pages WHERE url_id = ?",
        (target_id,),
    ) == [(200, "non_indexable", "noindex", "https://example.test/b")]

    detail = {"canonical_url": "https://example.test/b", "target_reason": "noindex"}
    _assert_canonical_results(crawl.path, [(source_id, detail)])


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_to_a_url_without_a_response(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site({"/a": Page(body='<link rel="canonical" href="/b">'), "/b": Page(body="", hang=True)})
    )
    result = crawl_result(server.url("/a"), timeout=1, retries=0)
    file = result.crawl_file
    source, target = server.url("/a"), server.url("/b")

    [(source_id, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert _target_outcome(file, target) == [("error", "timeout", 1, None, None)]
    assert [request.path for request in server.requests].count("/b") == 1
    assert result.summary.state == "completed"

    expected = [(source_id, {"canonical_url": target, "target_reason": "no_response"})]
    _assert_canonical_results(file, expected)
    materialised = query(
        file,
        "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'canonical-to-non-indexable'",
    )
    assert [(url_id, json.loads(detail)) for url_id, detail in materialised] == expected


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_target_robots_txt_preflight_fails(fixture_hosts: StartHosts) -> None:
    source, target = "http://site.test/a", "http://other.test/b"
    hosts = fixture_hosts(
        Site({"/a": Page(body='<link rel="canonical" href="http://other.test/b">')}),
        Site({"/robots.txt": Robots("User-agent: *\nAllow: /\n", hang=True), "/b": Page(body="B")}),
    )
    result = crawl_result(source, resolver=hosts.resolver, timeout=1, retries=0)
    file = result.crawl_file

    [(_, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert _target_outcome(file, target) == [("error", "timeout", 0, None, None)]
    assert [request.path for request in hosts.other.requests] == ["/robots.txt"]
    _assert_canonical_results(file, [])


def _rows_for_b(result: UrlResult) -> tuple[int, ...]:
    return (result.url_id,) if result.url.endswith("/b") and result.response else ()


def _reject_target_rows(_connection: Connection, rows: Sequence[int]) -> None:
    raise ValueError(f"Cannot record the test row for URL {rows[0]}")


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_target_response_could_not_be_recorded(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site({"/a": Page(body='<link rel="canonical" href="/b">'), "/b": Page(body="<p>B</p>")})
    )
    hooks = default_hooks()
    hooks = replace(
        hooks, handlers=(*hooks.handlers, handler("reject_b", _rows_for_b, _reject_target_rows))
    )
    result = crawl_result(server.url("/a"), hooks)
    file = result.crawl_file
    source, target = server.url("/a"), server.url("/b")

    [(_, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert _target_outcome(file, target) == [("error", "record_failed", 1, None, None)]
    assert [request.path for request in server.requests].count("/b") == 1
    assert [(warning.code, warning.details.get("count")) for warning in result.warnings] == [
        ("record_failed", 1)
    ]
    _assert_canonical_results(file, [])


@pytest.mark.parametrize(
    ("status", "blocked", "is_page", "expected_reason"),
    [
        pytest.param(301, True, True, "blocked_by_robots_txt", id="blocked-page-redirect"),
        pytest.param(301, True, False, "blocked_by_robots_txt", id="blocked-non-page-redirect"),
        pytest.param(301, False, False, "redirected", id="non-page-redirect"),
        pytest.param(404, False, False, "client_error", id="non-page-4xx"),
        pytest.param(599, False, False, "server_error", id="non-page-5xx"),
        pytest.param(999, False, False, "client_error", id="non-page-bot-block"),
    ],
)
@pytest.mark.usefixtures("temp_workspace")
def test_canonical_target_indexability_precedence(
    fixture_site: StartSite, status: int, blocked: bool, is_page: bool, expected_reason: str
) -> None:
    content_type = "text/html" if is_page else "text/plain"
    robots_rule = "Disallow: /b" if blocked else "Allow: /"
    server = fixture_site(
        Site(
            {
                "/robots.txt": Robots(f"User-agent: *\n{robots_rule}\n"),
                "/a": Page(body='<link rel="canonical" href="/b">'),
                "/b": Status(status, content_type=content_type),
            }
        )
    )
    source, target = server.url("/a"), server.url("/b")
    file = crawl_result(source, ignore_robots=True, retries=0).crawl_file

    [(source_id, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert query(
        file,
        "SELECT urls.status_code, urls.blocked_by_robots_txt, urls.parsed, "
        "pages.indexability, pages.indexability_status FROM urls "
        "LEFT JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
        (target,),
    ) == [
        (status, int(blocked), 0, "non_indexable", "blocked_by_robots_txt")
        if is_page
        else (status, int(blocked), 0, None, None)
    ]
    _assert_canonical_results(
        file, [(source_id, {"canonical_url": target, "target_reason": expected_reason})]
    )


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_to_an_indexable_page(fixture_site: StartSite) -> None:
    _assert_indexable_target(
        fixture_site,
        "/b",
        Page(body="<title>Target</title>", content_type="text/html"),
        (200, "text/html", 1, 1, "indexable", None),
    )


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_to_a_non_html_200_response(fixture_site: StartSite) -> None:
    _assert_indexable_target(
        fixture_site,
        "/doc.pdf",
        Status(200, body="%PDF-1.7", content_type="application/pdf"),
        (200, "application/pdf", 1, 0, None, None),
    )


def _assert_indexable_target(
    fixture_site: StartSite, path: str, route: Page | Status, expected_target: tuple[object, ...]
) -> None:
    server = fixture_site(
        Site({"/a": Page(body=f'<link rel="canonical" href="{path}">'), path: route})
    )
    source, target = server.url("/a"), server.url(path)
    result = crawl_result(source)
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert sorted(request.path for request in server.requests) == ["/a", path, "/robots.txt"]
    [(_, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert query(
        file,
        "SELECT urls.status_code, urls.content_type, urls.attempt_count, pages.url_id IS NOT NULL, "
        "pages.indexability, pages.indexability_status FROM urls "
        "LEFT JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
        (target,),
    ) == [expected_target]
    _assert_canonical_results(file, [])


@pytest.mark.usefixtures("temp_workspace")
def test_canonical_target_blocked_by_robots_txt_is_never_requested(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nDisallow: /b\n"),
                "/a": Page(body='<link rel="canonical" href="/b">'),
                "/b": Page(body="<title>Target</title>"),
            }
        )
    )
    source, target = server.url("/a"), server.url("/b")
    result = crawl_result(source, retries=0)
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert [(request.method, request.path) for request in server.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/a"),
    ]
    [(source_id, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert query(
        file,
        "SELECT urls.fetch_state, urls.skip_reason, urls.attempt_count, "
        "urls.blocked_by_robots_txt, pages.url_id FROM urls "
        "LEFT JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
        (target,),
    ) == [("skipped", "blocked_by_robots_txt", 0, 1, None)]
    _assert_canonical_results(
        file, [(source_id, {"canonical_url": target, "target_reason": "blocked_by_robots_txt"})]
    )


@pytest.mark.parametrize(
    ("check_external", "max_urls", "crawl_state", "target_state", "skip_reason"),
    [
        pytest.param(False, None, "completed", "skipped", "external_not_checked", id="skipped"),
        pytest.param(True, 1, "stopped", "queued", None, id="queued-at-url-limit"),
    ],
)
@pytest.mark.usefixtures("temp_workspace")
def test_canonical_target_never_requested(
    fixture_hosts: StartHosts,
    check_external: bool,
    max_urls: int | None,
    crawl_state: str,
    target_state: str,
    skip_reason: str | None,
) -> None:
    source, target = "http://site.test/a", "http://other.test/b"
    hosts = fixture_hosts(
        Site({"/a": Page(body='<link rel="canonical" href="http://other.test/b">')}),
        Site({"/b": Page(body="<title>Target</title>")}),
    )
    result = crawl_result(
        source, resolver=hosts.resolver, check_external=check_external, max_urls=max_urls
    )
    file = result.crawl_file

    assert result.summary.state == crawl_state
    assert [request.path for request in hosts.site.requests] == ["/robots.txt", "/a"]
    assert hosts.other.requests == ()
    [(_, canonical)] = _source_canonicals(file, source)
    assert canonical == target
    assert query(
        file,
        "SELECT fetch_state, skip_reason, attempt_count, status_code, blocked_by_robots_txt "
        "FROM urls WHERE url = ?",
        (target,),
    ) == [(target_state, skip_reason, 0, None, None)]
    _assert_canonical_results(file, [])


def _source_canonicals(file: Path, source: str) -> list[tuple[int, str | None]]:
    return query(
        file,
        "SELECT pages.url_id, pages.canonical_url FROM pages "
        "JOIN urls ON urls.id = pages.url_id WHERE urls.url = ?",
        (source,),
    )


def _target_outcome(file: Path, target: str) -> list[tuple[object, ...]]:
    return query(
        file,
        "SELECT fetch_state, fetch_error, attempt_count, urls.status_code, pages.url_id "
        "FROM urls LEFT JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
        (target,),
    )


def _assert_canonical_results(file: Path, expected: list[tuple[int, dict[str, str]]]) -> None:
    rule_id = "canonical-to-non-indexable"
    [rule] = [rule for rule in RULES if rule.id == rule_id]
    evaluated = evaluate_rule(file, rule)
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,))
    reproduced = [(url_id, json.loads(detail)) for url_id, detail in query(file, sql)]
    assert ([(row.url_id, row.detail) for row in evaluated], reproduced) == (expected, expected)


def _record_seed_page(
    writer: CrawlWriter, url: str, page: PageRow, *, redirect: Redirect | None = None
) -> int:
    url_id = writer.run(record_seed(NormalizedUrl(url), is_internal=True, in_scope=True))
    writer.run(
        record_fetched(
            FetchedUrl(
                url_id=url_id,
                provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
                status_code=page.status_code,
                content_type=page.content_type,
                fetched_at=STARTED_AT,
                response_time_ms=page.response_time_ms,
                parsed=redirect is None,
                attempt_count=1,
                redirect=redirect,
                rows=(
                    HandlerRows(
                        write_pages, (replace(page, url_id=url_id, crawl_timestamp=STARTED_AT),)
                    ),
                ),
            )
        )
    )
    return url_id
