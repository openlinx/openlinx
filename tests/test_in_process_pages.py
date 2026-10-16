"""The in-process double crosses a pickle as the pool does (design D1 of 026-add-parse-pool)."""

import pickle

import pytest

from spider.crawl.pages import PageSettings
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl, strip_params_pattern
from spider.services.hooks import default_hooks

INNER_HELPERS = """
import asyncio
from datetime import UTC, datetime

import msgspec

from spider.aio import loop_factory
from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import PageSettings, extractor
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl
from spider.services import crawling

SEED = NormalizedUrl("https://site.test/")
RESPONSE = FetchResult(
    status_code=200,
    headers=(("Content-Type", "text/html; charset=utf-8"),),
    body=b"<title>Home</title>",
    fetched_at=datetime(2026, 10, 16, tzinfo=UTC),
    response_time_ms=0,
)


class Marker(msgspec.Struct, frozen=True):
    pass


def prepared(built):
    async def prepare():
        executor = crawling.default_page_executor()
        await executor.start(
            PageSettings(scope=scope_rules(SEED), extractors=(built,), strip_params=None)
        )
        try:
            return await executor.prepare(SEED, RESPONSE)
        finally:
            await executor.close()

    return asyncio.run(prepare(), loop_factory=loop_factory)
"""

UNPICKLABLE_OUTPUT = """
def _local_class(tree, page, config):
    class Local(msgspec.Struct, frozen=True):
        pass

    return Local()


def test_an_output_of_a_local_class():
    prepared(extractor("local_class", _local_class, None))
"""

LOCAL_EXTRACTOR = """
def test_a_local_extractor():
    def local(tree, page, config):
        return Marker()

    prepared(extractor("local", local, None))
"""

LOCAL_CONFIG = """
def _marker(tree, page, config):
    return Marker()


def test_a_config_of_a_local_class():
    class Local(msgspec.Struct, frozen=True):
        pass

    prepared(extractor("marker", _marker, Local()))
"""


def inner_run(pytester: pytest.Pytester, test: str) -> pytest.RunResult:
    pytester.makepyfile(INNER_HELPERS + test)
    return pytester.runpytest(
        "-p", "tests.support.page_executor", "-o", "asyncio_default_fixture_loop_scope=function"
    )


def test_an_output_that_cannot_be_pickled_fails_the_test(pytester: pytest.Pytester) -> None:
    result = inner_run(pytester, UNPICKLABLE_OUTPUT)

    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_an_output_of_a_local_class*",
            "Cannot cross the parse pool: the output of local_class on https://site.test/: "
            "PicklingError: *",
        ]
    )


def test_an_extractor_that_cannot_be_pickled_fails_the_test(pytester: pytest.Pytester) -> None:
    result = inner_run(pytester, LOCAL_EXTRACTOR)

    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_a_local_extractor*",
            "Cannot cross the parse pool: the settings snapshot: PicklingError: *",
        ]
    )


def test_an_extractor_config_that_cannot_be_pickled_fails_the_test(
    pytester: pytest.Pytester,
) -> None:
    result = inner_run(pytester, LOCAL_CONFIG)

    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_a_config_of_a_local_class*",
            "Cannot cross the parse pool: the settings snapshot: PicklingError: *",
        ]
    )


def test_the_built_in_extractors_reach_a_worker_as_they_are() -> None:
    # An Extractor's equality takes in its config, and the snapshot's pattern of strip_params.
    settings = PageSettings(
        scope=scope_rules(NormalizedUrl("https://site.test/")),
        extractors=default_hooks().extractors,
        strip_params=strip_params_pattern(["utm_*"]),
    )

    assert pickle.loads(pickle.dumps(settings, pickle.HIGHEST_PROTOCOL)) == settings  # noqa: S301
