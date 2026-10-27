"""Crawling the fixture site in tests (020-add-crawl-core, seam 3+6)."""

from collections.abc import Callable
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from typing import Any

from aiohttp.abc import AbstractResolver

from spider.cli.app import build_app
from spider.clock import Clock, SystemClock
from spider.crawl.engine.hooks import Hooks
from spider.crawl.fetch.fetcher import Fetcher, FetcherFactory, aiohttp_fetcher
from spider.crawl.pages.preparation import PageExecutor
from spider.output.reporter import Collected, Reporter
from spider.services.crawling import CrawlRequest, CrawlResult, plan_crawl, start_crawl
from spider.services.hooks import default_hooks
from spider.store.records import SecretNames
from tests.support.app import settings_tables
from tests.support.cli import run_cli


def crawled(*args: str) -> Path:
    """Runs `spider crawl` with `args` and returns the crawl file its result names."""
    result = run_cli("crawl", *args)
    if result.exit_code != 0:
        last = result.stderr.splitlines()[-1:] or [b""]
        raise AssertionError(f"spider crawl exited {result.exit_code}: {last[0][:2000]!r}")
    return Path(result.json()["crawl_file"])


def crawl_result(
    seed: str,
    hooks: Hooks | None = None,
    *,
    resolver: AbstractResolver | None = None,
    trust_anchors: str | None = None,
    pages: Callable[[], PageExecutor] | None = None,
    reporter: Reporter | None = None,
    clock: Clock | None = None,
    fetcher: Fetcher | None = None,
    **crawl: Any,
) -> CrawlResult:
    """Crawls through the Crawl Service, which alone takes test hooks, the DNS resolver hook,
    the test CA's trust anchors and the page executor.

    `crawl` holds settings of the [crawl] table, as their flags would give them. Like the CLI, it
    crawls into the Workspace of the current folder, which `temp_workspace` sets, on the real
    clock unless `clock` is given: a FakeClock is for timing scenarios with a fake Fetcher, and
    its time jumps to each sleep's wake once the loop is quiet.
    """
    request = CrawlRequest(
        seed=seed,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=None,
        command_argv=["spider", "crawl", seed],
        secret_names=SecretNames(),
        flags={"crawl": crawl},
    )
    plan = plan_crawl(request, settings_tables(build_app()))
    return start_crawl(
        plan,
        clock or SystemClock(),
        reporter or Collected(),
        hooks or default_hooks(),
        pages=pages,
        fetchers=_fetchers(resolver, trust_anchors, fetcher),
    )


def _fetchers(
    resolver: AbstractResolver | None, trust_anchors: str | None, fetcher: Fetcher | None
) -> FetcherFactory:
    if fetcher is None:
        return partial(aiohttp_fetcher, resolver=resolver, trust_anchors=trust_anchors)
    return lambda policy, clock: nullcontext(fetcher)
