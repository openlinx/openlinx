"""The Crawl's warning log (020-add-crawl-core D10; seams 2 and 3)."""

from spider.crawl.engine.warning_log import WarningLog
from spider.output.codes import (
    DECLARED,
    MAX_URLS_REACHED,
    ROBOTS_UNREACHABLE,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Collected
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.crawling import crawl_result
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

    results = [
        crawl_result(down.url("/"), ignore_robots=True),
        crawl_result(closed.url("/")),
        crawl_result("http://www.site.test/", resolver=www.resolver),
    ]

    assert sorted(
        (warning.code, _ONCE_PER[warning.code] in warning.details)
        for result in results
        for warning in result.warnings
        if warning.code in _ONCE_PER
    ) == [
        ("possible_blocking", True),
        ("robots_unreachable", True),
        ("seed_base_mismatch", True),
        ("seed_blocked_by_robots_txt", True),
    ]
