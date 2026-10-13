"""The Crawl Service: a foreground Spider-mode Crawl (020-add-crawl-core D11, D15)."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.aio import loop_factory
from spider.clock import Clock
from spider.crawl.context import CrawlContext
from spider.crawl.engine import run_crawl
from spider.crawl.fetcher import aiohttp_fetcher
from spider.crawl.urls import InvalidUrl, InvalidUrlReason, NormalizedUrl, parse_seed
from spider.output.codes import INVALID_URL
from spider.output.diagnostics import SpiderError
from spider.output.reporter import Reporter
from spider.services.crawls import create_crawl
from spider.store.records import CrawlFile, NewCrawl, SecretNames
from spider.store.settings import StoreSettings
from spider.workspace.discovery import resolve_workspace
from spider.workspace.settings import load_settings
from spider.workspace.tables import SettingsTables

_SEED_PROBLEMS: Mapping[InvalidUrlReason, str] = {
    "malformed": "is not a valid URL",
    "unsupported_scheme": "is not an http or https URL",
    "missing_host": "has no host",
    "invalid_host": "has a host that is not valid",
}


@dataclass(frozen=True, kw_only=True)
class CrawlRequest:
    seed: str
    cwd: Path
    home: Path
    workspace: Path | None
    command_argv: Sequence[str]
    secret_names: SecretNames


@dataclass(frozen=True)
class CrawlPlan:
    seed: NormalizedUrl
    new_crawl: NewCrawl


@dataclass(frozen=True, kw_only=True)
class CrawlResult:
    crawl_id: str
    crawl_file: Path

    def to_json(self) -> dict[str, Any]:
        return {"crawl_id": self.crawl_id, "crawl_file": str(self.crawl_file)}


def plan_crawl(request: CrawlRequest, tables: SettingsTables) -> CrawlPlan:
    """Validation and config resolution, before anything is created (design D11)."""
    seed = parse_seed(request.seed)
    if isinstance(seed, InvalidUrl):
        raise _invalid_seed(request.seed, seed.reason)
    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    settings = load_settings(workspace, tables)
    settings_file = workspace.settings_file if workspace.settings_file.is_file() else None
    new_crawl = NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        # As given: the urls row holds the normalised Seed.
        seeds=[request.seed],
        command_argv=request.command_argv,
        cwd=request.cwd,
        config={},
        secret_names=request.secret_names,
        journal_setting=settings.table(StoreSettings).journal_mode,
        settings_file=settings_file,
    )
    return CrawlPlan(seed, new_crawl)


def start_crawl(plan: CrawlPlan, clock: Clock, reporter: Reporter) -> CrawlResult:
    crawl_file = create_crawl(plan.new_crawl, clock, reporter)
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(_crawl(plan, crawl_file, clock, reporter))
    return CrawlResult(crawl_id=crawl_file.id, crawl_file=crawl_file.path)


async def _crawl(plan: CrawlPlan, crawl_file: CrawlFile, clock: Clock, reporter: Reporter) -> None:
    async with crawl_context(crawl_file, clock, reporter) as context:
        await run_crawl(context, plan.seed)


@asynccontextmanager
async def crawl_context(
    crawl_file: CrawlFile, clock: Clock, reporter: Reporter
) -> AsyncIterator[CrawlContext]:
    """The one place a Crawl's context is built, and its resources closed (design D15)."""
    from spider.store.writer import CrawlWriter

    # Opening and closing the writer block, so they run off the event loop.
    writer = await asyncio.to_thread(CrawlWriter, crawl_file.path, clock)
    try:
        async with aiohttp_fetcher() as fetcher:
            yield CrawlContext(
                crawl_file=crawl_file,
                clock=clock,
                reporter=reporter,
                writer=writer,
                fetcher=fetcher,
            )
    finally:
        await asyncio.to_thread(writer.close)


def _invalid_seed(text: str, reason: InvalidUrlReason) -> SpiderError:
    details = {"reason": reason}
    if reason == "userinfo":
        # Never echoed: the user name and password would reach logs (design D13).
        return SpiderError(
            INVALID_URL,
            "The Seed holds a user name or password, which a crawled URL must not hold.",
            hint="Give the URL without them; --auth, planned for v0.2, will send credentials.",
            details=details,
        )
    return SpiderError(
        INVALID_URL,
        f"The Seed {text} {_SEED_PROBLEMS[reason]}.",
        hint="Give an http or https URL, or a host such as site.test, which gets https://.",
        details=details,
    )
