"""Crawling the fixture site in tests (020-add-crawl-core, seam 3+6)."""

from pathlib import Path
from typing import Any

from aiohttp.abc import AbstractResolver

from spider.cli.app import build_app
from spider.crawl.hooks import Hooks, default_hooks
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, CrawlResult, plan_crawl, start_crawl
from spider.store.records import SecretNames
from tests.support.app import settings_tables
from tests.support.cli import run_cli
from tests.support.clock import FakeClock


def crawled(*args: str) -> Path:
    """Runs `spider crawl` with `args` and returns the crawl file its result names."""
    result = run_cli("crawl", *args)
    if result.exit_code != 0:
        last = result.stderr.splitlines()[-1:] or [b""]
        raise AssertionError(f"spider crawl exited {result.exit_code}: {last[0][:2000]!r}")
    return Path(result.json()["crawl_file"])


def crawl_result(
    seed: str, hooks: Hooks | None = None, *, resolver: AbstractResolver | None = None, **crawl: Any
) -> CrawlResult:
    """Crawls through the Crawl Service, which alone takes test hooks and the DNS resolver hook.

    `crawl` holds settings of the [crawl] table, as their flags would give them.
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
    return start_crawl(plan, FakeClock(), Collected(), hooks or default_hooks(), resolver=resolver)
