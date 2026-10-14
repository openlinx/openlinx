"""The Crawl Service: a foreground Spider-mode Crawl (020-add-crawl-core D11, D15)."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from spider.aio import loop_factory
from spider.clock import Clock
from spider.crawl.context import CrawlContext
from spider.crawl.engine import run_crawl
from spider.crawl.fetcher import aiohttp_fetcher
from spider.crawl.pages import InProcessExecutor, PageSettings
from spider.crawl.scope import ScopeRules, scope_rules
from spider.crawl.urls import InvalidUrl, InvalidUrlReason, NormalizedUrl, parse_seed
from spider.output.codes import INVALID_URL
from spider.output.diagnostics import Diagnostic, SpiderError
from spider.output.events import timestamp_text
from spider.output.reporter import Reporter
from spider.services.crawls import create_crawl
from spider.store.records import CrawlFile, CrawlSummary, NewCrawl, SecretNames, UrlCounts
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
    # Settings given as flags, by table: they override the settings file (010 D2).
    flags: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class CrawlPlan:
    seed: NormalizedUrl
    scope: ScopeRules
    new_crawl: NewCrawl


@dataclass(frozen=True, kw_only=True)
class CrawlResult:
    """Built at the end from the crawl file, never from counters kept while it ran (D10)."""

    crawl_id: str
    summary: CrawlSummary
    ended_at: datetime
    counts: UrlCounts
    crawl_file: Path
    warnings: tuple[Diagnostic, ...]

    def to_json(self) -> dict[str, Any]:
        summary, counts = self.summary, self.counts
        started_at = datetime.fromisoformat(summary.started_at)
        return {
            "crawl_id": self.crawl_id,
            "state": summary.state,
            "stop_reason": summary.stop_reason,
            "crawl_mode": summary.crawl_mode,
            "seed": summary.seed,
            "seed_count": summary.seed_count,
            "section_crawl": summary.section_crawl,
            "started_at": summary.started_at,
            "ended_at": timestamp_text(self.ended_at),
            "duration_s": round((self.ended_at - started_at).total_seconds(), 3),
            "urls": {
                "discovered": counts.discovered,
                "fetched": counts.fetched,
                "errors": counts.errors,
                "skipped": counts.skipped,
                "queued": counts.queued,
            },
            "pages": counts.pages,
            "status_classes": {
                "2xx": counts.status_2xx,
                "3xx": counts.status_3xx,
                "4xx": counts.status_4xx,
                "5xx": counts.status_5xx,
                "other": counts.status_other,
            },
            "crawl_file": str(self.crawl_file),
            "warnings": [warning.to_json() for warning in self.warnings],
        }


class WarningLog:
    """The Crawl's Reporter: passes everything on, and keeps the warnings for the result (D10)."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter
        self.warnings: list[Diagnostic] = []

    def warn(self, diagnostic: Diagnostic) -> None:
        self.warnings.append(diagnostic)
        self._reporter.warn(diagnostic)

    def event(self, name: str, **data: Any) -> None:
        self._reporter.event(name, **data)


def plan_crawl(request: CrawlRequest, tables: SettingsTables) -> CrawlPlan:
    """Validation and config resolution, before anything is created (design D11)."""
    seed = parse_seed(request.seed)
    if isinstance(seed, InvalidUrl):
        raise _invalid_seed(request.seed, seed.reason)
    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    settings = load_settings(workspace, tables, request.flags)
    settings_file = workspace.settings_file if workspace.settings_file.is_file() else None
    new_crawl = NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        # As given: the urls row holds the normalised Seed.
        seeds=[request.seed],
        command_argv=request.command_argv,
        cwd=request.cwd,
        # Every registered table, resolved (design D11).
        config=settings.root.model_dump(mode="json"),
        secret_names=request.secret_names,
        journal_setting=settings.table(StoreSettings).journal_mode,
        settings_file=settings_file,
    )
    return CrawlPlan(seed, scope_rules(seed), new_crawl)


def start_crawl(plan: CrawlPlan, clock: Clock, reporter: Reporter) -> CrawlResult:
    reporter = log = WarningLog(reporter)
    crawl_file = create_crawl(plan.new_crawl, clock, reporter)
    reporter.event(
        "crawl_started",
        crawl_id=crawl_file.id,
        crawl_mode=plan.new_crawl.crawl_mode,
        seed_count=len(plan.new_crawl.seeds),
        crawl_file=str(crawl_file.path),
    )
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        summary, counts = runner.run(_crawl(plan, crawl_file, clock, reporter))
    return CrawlResult(
        crawl_id=crawl_file.id,
        summary=summary,
        ended_at=clock.now(),
        counts=counts,
        crawl_file=crawl_file.path,
        warnings=tuple(log.warnings),
    )


async def _crawl(
    plan: CrawlPlan, crawl_file: CrawlFile, clock: Clock, reporter: Reporter
) -> tuple[CrawlSummary, UrlCounts]:
    from spider.store.crawls import crawl_summary, record_state
    from spider.store.urls import url_counts

    async with crawl_context(crawl_file, plan.scope, clock, reporter) as context:
        await run_crawl(context, plan.seed)
        writer = context.writer
        await writer.run_async(record_state("completed", clock.now()))
        return await writer.run_async(crawl_summary()), await writer.run_async(url_counts())


@asynccontextmanager
async def crawl_context(
    crawl_file: CrawlFile, scope: ScopeRules, clock: Clock, reporter: Reporter
) -> AsyncIterator[CrawlContext]:
    """The one place a Crawl's context is built, and its resources closed (design D15)."""
    from spider.store.writer import CrawlWriter

    # Opening and closing the writer block, so they run off the event loop.
    writer = await asyncio.to_thread(CrawlWriter, crawl_file.path, clock)
    try:
        async with aiohttp_fetcher(clock) as fetcher:
            yield CrawlContext(
                crawl_file=crawl_file,
                scope=scope,
                clock=clock,
                reporter=reporter,
                writer=writer,
                fetcher=fetcher,
                pages=InProcessExecutor(PageSettings(scope)),
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
