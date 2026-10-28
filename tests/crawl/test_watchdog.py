"""The watchdog, a backstop behind the Fetcher's own deadline (020-add-crawl-core D16)."""

import pytest

from spider.crawl.fetch.requester import watchdog_seconds
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

# An hour away: a hang that the Fetcher's own deadline does not cover.
NEVER = 3600


@pytest.mark.parametrize(
    ("request_deadline", "watchdog"), [(20, 120), (90, 120), (91, 121), (200, 230)]
)
def test_the_watchdog_is_120_seconds_or_30_more_than_the_request_deadline(
    request_deadline: float, watchdog: float
) -> None:
    assert watchdog_seconds(request_deadline) == watchdog


def test_a_stuck_request_is_ended_by_the_watchdog(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage('<a href="/stuck">S</a><a href="/ok">O</a>'),
        "/stuck": FakePage("<p>S</p>", delay=NEVER),
        "/ok": FakePage("<p>O</p>"),
    }

    result = crawl_result("http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages))

    # /stuck started with / at virtual 0, and its row keeps when it started, as any request's does.
    started = query(
        result.crawl_file,
        "SELECT COUNT(DISTINCT fetched_at) FROM urls WHERE url IN (?, ?)",
        ["http://site.test/", "http://site.test/stuck"],
    )
    assert (
        query(
            result.crawl_file,
            "SELECT url, fetch_state, fetch_error, fetch_error_message FROM urls ORDER BY id",
        ),
        started,
        result.summary.state,
    ) == (
        [
            ("http://site.test/", "fetched", None, None),
            ("http://site.test/stuck", "error", "watchdog", "No response within 120 seconds"),
            ("http://site.test/ok", "fetched", None, None),
        ],
        [(1,)],
        "completed",
    )


def test_a_stuck_robots_txt_request_gives_its_origins_urls_the_watchdog_error(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage('<a href="http://www.site.test/page">P</a>'),
        "http://www.site.test/robots.txt": FakePage("", delay=NEVER),
    }
    fetcher = FakeFetcher(clock, pages)

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher)

    assert (
        query(
            result.crawl_file,
            "SELECT fetch_state, fetch_error FROM urls WHERE url = 'http://www.site.test/page'",
        ),
        "/page" in {path for path, _ in fetcher.starts},
    ) == ([("error", "watchdog")], False)
