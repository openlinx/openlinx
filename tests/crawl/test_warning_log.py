"""The Crawl's warning log (020-add-crawl-core D10; seams 2, 3 and 3+6)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from spider.crawl.engine.crawl_warnings import handler_failure
from spider.crawl.engine.hooks import UrlResult
from spider.crawl.engine.outcomes import Outcomes, Recorded, provenance_of
from spider.crawl.engine.stop import StopSignal
from spider.crawl.engine.warning_log import WarningLog
from spider.crawl.urls import NormalizedUrl
from spider.output.codes import (
    DECLARED,
    MAX_URLS_REACHED,
    ROBOTS_UNREACHABLE,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Collected
from spider.store.records import FetchedUrl, LinkType, NewUrl, Provenance, QueuedUrl, SkippedUrl
from spider.store.urls import queued_batch, record_fetched, record_seed, record_skipped
from spider.store.writer import CrawlWriter
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, create_any_crawl, query
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


def _fetched(url_id: int, provenance: Provenance, *discovered: NewUrl) -> FetchedUrl:
    return FetchedUrl(
        url_id=url_id,
        provenance=provenance,
        status_code=200,
        content_type="text/html",
        fetched_at=datetime(2026, 10, 27, tzinfo=UTC),
        response_time_ms=1,
        parsed=True,
        discovered=discovered,
    )


def _new(url: str, discovered_via: LinkType = "hyperlink") -> NewUrl:
    return NewUrl(
        url=NormalizedUrl(url), discovered_via=discovered_via, is_internal=True, in_scope=True
    )


def _skipped(queued: QueuedUrl, failure: Diagnostic) -> Recorded:
    """A URL that robots.txt blocks, decided on its queued row, whose handler failed."""
    result = UrlResult(
        url_id=queued.id,
        url=queued.url,
        crawl_depth=queued.crawl_depth,
        discovered_via=queued.discovered_via,
        found_on_url_id=queued.found_on_url_id,
        is_internal=True,
        in_scope=True,
        fetch_state="skipped",
        skip_reason="blocked_by_robots_txt",
        blocked_by_robots_txt=True,
    )
    skipped = SkippedUrl(
        url_id=queued.id,
        skip_reason="blocked_by_robots_txt",
        provenance=provenance_of(result),
        blocked_by_robots_txt=True,
    )
    return Recorded(result, record_skipped(skipped), failure)


async def test_a_skip_that_a_raise_overtook_counts_its_handler_failure_once_decided_again(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)
    log = WarningLog(Collected())
    seed = NormalizedUrl("http://site.test/")
    page_at = Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(seed, is_internal=True, in_scope=True))
        page, late = _new("http://site.test/a"), _new("http://site.test/late.html", "image")
        writer.run(record_fetched(_fetched(seed_id, page_at, page, late)))
        a_at = Provenance(crawl_depth=1, discovered_via="hyperlink", found_on_url_id=seed_id)
        writer.run(record_fetched(_fetched(seed_id + 1, a_at, _new("http://site.test/x"))))
        (dispatched,) = writer.run(queued_batch(2, 0, 10))
        late_at = Provenance(crawl_depth=1, discovered_via="image", found_on_url_id=seed_id)
        # The late check's image Link raises /x while its skip is on its way.
        image = _new("http://site.test/x", "image")
        writer.run(record_fetched(_fetched(seed_id + 2, late_at, image)))
        outcomes = Outcomes(writer, log, StopSignal())
        failure = handler_failure(dispatched.url, [("pages", ValueError("no title"))])
        await outcomes.submit(_skipped(dispatched, failure))
        await outcomes.settled()
        # Decided again on its raised row, its handlers fail again.
        (again,) = writer.run(queued_batch(2, 0, 10))
        await outcomes.submit(_skipped(again, failure))
        await outcomes.settled()

    assert (
        [(warning.code, warning.details["count"]) for warning in log.warnings],
        query(crawl.path, "SELECT fetch_state, discovered_via FROM urls WHERE id = ?", [again.id]),
    ) == ([("handler_failed", 1)], [("skipped", "image")])


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
