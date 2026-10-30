"""Crawling the fixture site in tests (020-add-crawl-core, seam 3+6)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aiohttp.abc import AbstractResolver

from openlinx.cli.app import build_app
from openlinx.clock import Clock, SystemClock
from openlinx.crawl.engine.hooks import Hooks
from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.fetch.fetcher import Fetcher
from openlinx.crawl.pages.preparation import PageExecutor
from openlinx.output.reporter import Collected, Reporter
from openlinx.services.crawling import (
    CrawlOverrides,
    CrawlRequest,
    CrawlResult,
    continue_crawl,
    plan_crawl,
    start_crawl,
)
from openlinx.services.hooks import default_hooks
from openlinx.store.records import CrawlFile, SecretNames
from openlinx.workspace.tables import SettingsTables
from tests.support.app import settings_tables
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.fetcher import FakeFetcher, FakePage


def crawled(*args: str) -> Path:
    """Runs `linx crawl` with `args` and returns the crawl file its result names."""
    result = run_cli("crawl", *args)
    if result.exit_code != 0:
        last = result.stderr.splitlines()[-1:] or [b""]
        raise AssertionError(f"linx crawl exited {result.exit_code}: {last[0][:2000]!r}")
    return Path(result.json()["crawl_file"])


def crawl_result(
    seed: str,
    hooks: Hooks | None = None,
    *,
    resolver: AbstractResolver | None = None,
    pages: Callable[[], PageExecutor] | None = None,
    reporter: Reporter | None = None,
    clock: Clock | None = None,
    fetcher: Fetcher | None = None,
    stop: StopSignal | None = None,
    tables: SettingsTables | None = None,
    **crawl: Any,
) -> CrawlResult:
    """Crawls through the Crawl Service, which alone takes test hooks, the DNS resolver hook
    and the page executor.

    `crawl` holds settings of the [crawl] table, as their flags would give them. Like the CLI, it
    crawls into the Workspace of the current folder, which `temp_workspace` sets, on the real
    clock unless `clock` is given: a FakeClock is for timing scenarios with a fake Fetcher, and
    its time jumps to each sleep's wake once the loop is quiet. `tables` are the settings
    tables of another app, such as `example_app()`'s; their secret settings are redacted as the
    CLI redacts them.
    """
    tables = tables or settings_tables(build_app())
    request = CrawlRequest(
        seed=seed,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=None,
        command_argv=["linx", "crawl", seed],
        secret_names=SecretNames(settings=tables.secret_settings()),
        flags={"crawl": crawl},
    )
    plan = plan_crawl(request, tables)
    return start_crawl(
        plan,
        clock or SystemClock(),
        reporter or Collected(),
        hooks or default_hooks(),
        resolver=resolver,
        pages=pages,
        fetcher=fetcher,
        stop=stop,
    )


def continued(
    crawl: CrawlResult,
    overrides: CrawlOverrides | None = None,
    hooks: Hooks | None = None,
    *,
    resolver: AbstractResolver | None = None,
    reporter: Reporter | None = None,
    clock: Clock | None = None,
    fetcher: Fetcher | None = None,
    stop: StopSignal | None = None,
) -> CrawlResult:
    """Continues the Crawl that `crawl` ended, through the Crawl Service, as 060's resume does."""
    return continue_crawl(
        CrawlFile(crawl.crawl_id, crawl.crawl_file),
        overrides or CrawlOverrides(),
        clock or SystemClock(),
        reporter or Collected(),
        hooks or default_hooks(),
        resolver=resolver,
        fetcher=fetcher,
        stop=stop,
    )


def stopped_with_an_error() -> Path:
    """A Crawl that its URL limit stopped after /a got no response, as a continue finds it."""
    clock = FakeClock()
    pages = {
        "/": FakePage('<a href="/a">A</a><a href="/b">B</a>'),
        "/a": FakePage("", fails="connection_refused"),
    }
    fetcher = FakeFetcher(clock, pages)
    return crawl_result("http://site.test/", clock=clock, fetcher=fetcher, max_urls=2).crawl_file
