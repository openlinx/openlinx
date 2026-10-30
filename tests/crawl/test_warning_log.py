"""The Crawl's warning log (020-add-crawl-core D10; seams 2, 3 and 3+6)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import Connection, text

from openlinx.crawl.engine.crawl_warnings import network_paused
from openlinx.crawl.engine.hooks import Hooks, UrlResult, handler
from openlinx.crawl.engine.warning_log import WarningLog
from openlinx.crawl.urls import NormalizedUrl
from openlinx.output.codes import (
    DECLARED,
    MAX_URLS_REACHED,
    ROBOTS_UNREACHABLE,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from openlinx.output.diagnostics import Diagnostic
from openlinx.output.reporter import Collected
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace


def _unreachable(origin: str, host: str) -> Diagnostic:
    return Diagnostic.of(
        ROBOTS_UNREACHABLE, f"{origin} is unreachable.", details={"origin": origin, "host": host}
    )


def test_a_warning_is_written_once_per_code_and_host() -> None:
    reporter = Collected()
    log = WarningLog(reporter)

    for origin, host in [
        ("http://site.test", "site.test"),
        ("https://site.test", "site.test"),
        ("http://www.site.test", "www.site.test"),
    ]:
        log.warn(_unreachable(origin, host))

    assert (
        [warning.details["origin"] for warning in log.warnings],
        [warning.details["origin"] for warning in reporter.warnings],
    ) == (
        ["http://site.test", "http://www.site.test"],
        ["http://site.test", "http://www.site.test"],
    )


def _blocked_seed(seed: str) -> Diagnostic:
    return Diagnostic.of(SEED_BLOCKED_BY_ROBOTS_TXT, f"{seed} is blocked.", details={"seed": seed})


def _limit(max_urls: int) -> Diagnostic:
    return Diagnostic.of(MAX_URLS_REACHED, "The limit.", details={"max_urls": max_urls})


def test_a_warning_is_kept_once_per_what_its_code_names() -> None:
    log = WarningLog(Collected())

    for warning in [
        _blocked_seed("http://a.test/"),
        _blocked_seed("http://b.test/"),
        _blocked_seed("http://a.test/"),
        _limit(5),
        _limit(10),
    ]:
        log.warn(warning)

    assert [(warning.code, *warning.details.values()) for warning in log.warnings] == [
        ("seed_blocked_by_robots_txt", "http://a.test/"),
        ("seed_blocked_by_robots_txt", "http://b.test/"),
        ("max_urls_reached", 5),
        ("max_urls_reached", 10),
    ]


_ONCE_PER = {code.code: code.once_per for code in DECLARED if code.once_per is not None}
# A site that answers 503 for robots.txt, crawled anyway, whose Pages all answer 403.
_DOWN = Site(
    routes={
        "/robots.txt": Status(503),
        "/": Page(body="".join(f'<a href="/p/{n}">{n}</a>' for n in range(12))),
        **{f"/p/{n}": Status(403) for n in range(12)},
    }
)


def test_a_warning_kept_once_per_a_detail_carries_that_detail(
    temp_workspace: TempWorkspace, fixture_site: StartSite, fixture_hosts: StartHosts
) -> None:
    down = fixture_site(_DOWN)
    closed = fixture_site(Site(routes={"/robots.txt": Robots("User-agent: *\nDisallow: /\n")}))
    www = fixture_hosts(
        Site(routes={"/": Page(body='<link rel="canonical" href="http://site.test/">')}),
        Site(routes={}),
    )
    moved = fixture_hosts(
        Site(
            routes={
                "/robots.txt": Redirect("http://nowhere.test/robots.txt"),
                "/": Page(body='<a href="/a">A</a>'),
                "/a": Page(body="<p>A</p>"),
            }
        ),
        Site(routes={}),
    )

    results = [
        crawl_result(down.url("/"), ignore_robots=True),
        crawl_result(closed.url("/")),
        crawl_result("http://www.site.test/", resolver=www.resolver),
        crawl_result("http://site.test/", resolver=moved.resolver),
    ]

    seen = sorted(
        (warning.code, _ONCE_PER[warning.code] in warning.details)
        for result in results
        for warning in result.warnings
        if warning.code in _ONCE_PER
    )

    # Every code kept once per a detail is among them, so a new one needs a crawl here.
    assert (seen, sorted(_ONCE_PER)) == (
        [
            ("possible_blocking", True),
            ("robots_redirect_failed", True),
            ("robots_unreachable", True),
            ("seed_base_mismatch", True),
            ("seed_blocked_by_robots_txt", True),
        ],
        [
            "possible_blocking",
            "robots_redirect_failed",
            "robots_unreachable",
            "seed_base_mismatch",
            "seed_blocked_by_robots_txt",
        ],
    )


@dataclass(frozen=True, slots=True)
class Seen:
    url_id: int


def _write_seen(connection: Connection, rows: Sequence[Seen]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_seen (url_id INTEGER)"))
    connection.execute(
        text("INSERT INTO test_seen VALUES (:url_id)"), [{"url_id": row.url_id} for row in rows]
    )


def _fails_on_x(result: UrlResult) -> tuple[Seen, ...]:
    if result.url == _RAISED:
        raise ValueError("no title")
    return ()


_RAISED = "http://other.test/x"


def test_a_skip_that_a_raise_overtook_counts_its_handler_failure_once_decided_again(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        # An image URL that answers HTML, late: its image Link raises other.test/x to a
        # Resource while the skip of its hyperlink waits for other.test's robots.txt.
        "/": FakePage('<a href="/a">A</a> <img src="/late.html">'),
        "/a": FakePage(f'<a href="{_RAISED}">X</a>'),
        "/late.html": FakePage(f'<img src="{_RAISED}">', delay=2),
        "http://other.test/robots.txt": FakePage(
            "User-agent: *\nDisallow: /\n", content_type="text/plain", delay=3
        ),
    }
    hooks = replace(Hooks(), handlers=(handler("titles", _fails_on_x, _write_seen),))

    result = crawl_result(
        "http://site.test/", hooks, clock=clock, fetcher=FakeFetcher(clock, pages)
    )

    assert (
        [(warning.code, warning.details["count"]) for warning in result.warnings],
        query(
            result.crawl_file,
            "SELECT fetch_state, skip_reason, discovered_via FROM urls WHERE url = ?",
            [_RAISED],
        ),
    ) == ([("handler_failed", 1)], [("skipped", "blocked_by_robots_txt", "image")])


_ROBOTS_DOWN = Site(
    routes={
        "/robots.txt": Status(503),
        "/": Page(body='<a href="/a">A</a> <a href="/b">B</a>'),
        "/a": Page(body="<p>A</p>"),
        "/b": Page(body="<p>B</p>"),
    }
)


def test_warnings_are_stored_as_diagnostics(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_ROBOTS_DOWN)

    stored = json.loads(crawl_row(crawled(server.url("/")))["warnings"])

    assert [
        (sorted(warning), warning["level"])
        for warning in stored
        if warning["code"] == "robots_unreachable"
    ] == [(["code", "details", "hint", "level", "message"], "warning")]


def test_the_crawl_file_keeps_every_warning_of_the_result(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_ROBOTS_DOWN)

    result = run_cli("crawl", server.url("/"), "--ignore-robots", "--max-urls", "1").json()
    stored = json.loads(crawl_row(Path(result["crawl_file"]))["warnings"])

    assert (stored, sorted(warning["code"] for warning in stored)) == (
        result["warnings"],
        ["max_urls_reached", "robots_unreachable"],
    )


def test_a_continuing_log_adds_its_pauses_to_the_stored_ones() -> None:
    reporter = Collected()
    stored = replace(
        network_paused(NormalizedUrl("http://site.test/")),
        details={"count": 1, "total_seconds": 30.0},
    )
    log = WarningLog(reporter, [stored])

    log.pause_began(network_paused(NormalizedUrl("http://site.test/")))
    log.pause_ended(5)

    assert (
        [(w.code, w.details["count"], w.details["total_seconds"]) for w in log.warnings],
        reporter.warnings,
    ) == ([("network_paused", 2, 35.0)], [])
