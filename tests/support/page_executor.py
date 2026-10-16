"""Crawls prepare Pages in process unless marked parse_pool (design D1 of 026-add-parse-pool).

The pool starts its workers for every Crawl, each a spawn process of Python with the parser, so a
CLI-level crawl test would pay their start and memory per crawl. Only the composition root's
choice is replaced, where the Crawl Service calls it; a test marked `parse_pool` keeps the pool.
What a worker would get or send crosses a pickle round trip here too, so a test in process still
fails when its hooks could not cross the pool.
"""

import pickle
from collections.abc import Iterator

import msgspec
import pytest

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import InProcessExecutor, PageSettings, PreparedPage
from spider.crawl.urls import NormalizedUrl
from spider.services import crawling


def _round_trip[T](value: T, what: str, failures: list[str]) -> T:
    try:
        copy: T = pickle.loads(pickle.dumps(value, pickle.HIGHEST_PROTOCOL))  # noqa: S301
    # Kept as it is, so the Crawl goes on and the test fails at its teardown.
    except Exception as error:
        failures.append(f"{what}: {type(error).__name__}: {error}")
        return value
    return copy


class _AsAWorker:
    """The in-process executor, given and giving only what crosses the pool's pipes."""

    backlog = 0
    workers = 0

    def __init__(self, failures: list[str]) -> None:
        self._failures = failures
        self._executor = InProcessExecutor()

    async def start(self, settings: PageSettings) -> None:
        await self._executor.start(_round_trip(settings, "the settings snapshot", self._failures))

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        page = await self._executor.prepare(url, response)
        outputs = tuple(
            (name, _round_trip(output, f"the output of {name} on {url}", self._failures))
            for name, output in page.outputs
        )
        return msgspec.structs.replace(page, outputs=outputs)

    async def close(self) -> None:
        await self._executor.close()


@pytest.fixture(autouse=True)
def in_process_pages(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("parse_pool") is not None:
        yield
        return
    failures: list[str] = []
    # Raises if the service stops calling this name, so the swap cannot silently lapse.
    monkeypatch.setattr(crawling, "default_page_executor", lambda: _AsAWorker(failures))
    yield
    if failures:
        pytest.fail("Cannot cross the parse pool: " + "; ".join(failures), pytrace=False)
