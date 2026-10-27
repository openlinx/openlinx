"""The fake Fetcher of the timing scenarios (020-add-crawl-core D15, 022-add-fetch-policy D9)."""

import asyncio

from spider.aio import loop_factory
from spider.crawl.fetch.fetcher import FetchResult, Request
from spider.crawl.urls import NormalizedUrl
from tests.support.clock import FakeClock
from tests.support.fetcher import FakeFetcher, FakePage


def _answers(fetcher: FakeFetcher, path: str, times: int) -> list[FetchResult]:
    async def fetch_all() -> list[FetchResult]:
        url = NormalizedUrl(f"http://site.test{path}")
        return [await fetcher.fetch(Request(url)) for _ in range(times)]

    return asyncio.run(fetch_all(), loop_factory=loop_factory)


def test_a_fake_page_answers_its_status_and_headers() -> None:
    fetcher = FakeFetcher(
        FakeClock(),
        {"/busy": FakePage("", status=429, headers=(("Retry-After", "7"),))},
    )

    [answer] = _answers(fetcher, "/busy", 1)

    assert (answer.status_code, answer.reason, answer.header("Retry-After")) == (
        429,
        "Too Many Requests",
        "7",
    )


def test_a_sequence_answers_in_turn_then_repeats_its_last() -> None:
    fetcher = FakeFetcher(
        FakeClock(), {"/flaky": (FakePage("", status=503), FakePage("<p>Back</p>"))}
    )

    answers = _answers(fetcher, "/flaky", 3)

    assert [answer.status_code for answer in answers] == [503, 200, 200]
