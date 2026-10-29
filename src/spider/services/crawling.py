"""The Crawl Service: a foreground Spider-mode Crawl (020-add-crawl-core D11, D15)."""

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, nullcontext, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp.abc import AbstractResolver

from spider.aio import loop_factory
from spider.clock import Clock
from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.dispatch import run_crawl
from spider.crawl.engine.hooks import Hooks, PassContext
from spider.crawl.engine.stop import StopSignal
from spider.crawl.engine.warning_log import WarningLog
from spider.crawl.fetch.fetcher import Fetcher, aiohttp_fetcher
from spider.crawl.pages.preparation import PageExecutor
from spider.crawl.scope import ScopeDecision, ScopeRules, scope_rules
from spider.crawl.settings import CrawlSettings
from spider.crawl.urls import (
    InvalidUrl,
    InvalidUrlReason,
    NormalizedUrl,
    parse_seed,
    strip_params_pattern,
    url_origin,
    url_path,
)
from spider.output.codes import (
    INVALID_PATTERN,
    INVALID_URL,
    SEED_OUT_OF_SCOPE,
    SUBFOLDER_IS_ROOT,
)
from spider.output.diagnostics import Diagnostic, SpiderError
from spider.output.events import timestamp_text
from spider.output.reporter import Reporter
from spider.services.crawls import create_crawl
from spider.services.hooks import default_page_executor
from spider.store.crawls import crawl_summary, record_state
from spider.store.records import (
    CrawlFile,
    CrawlState,
    CrawlSummary,
    NewCrawl,
    SecretNames,
    UrlCounts,
)
from spider.store.settings import StoreSettings
from spider.store.urls import url_counts
from spider.store.writer import CrawlWriter, CrawlWriterClosedError
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


@dataclass(frozen=True, kw_only=True)
class CrawlPlan:
    seed: NormalizedUrl
    settings: CrawlSettings
    scope: ScopeRules
    strip_params: re.Pattern[str] | None
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


def plan_crawl(request: CrawlRequest, tables: SettingsTables) -> CrawlPlan:
    """Validation and config resolution, before anything is created (design D11)."""
    # Checked before the Workspace is resolved, and stripped once the settings are read.
    _seed(request.seed, None)
    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    settings = load_settings(workspace, tables, request.flags)
    crawl_settings = settings.table(CrawlSettings)
    strip_params = strip_params_pattern(crawl_settings.strip_params)
    seed = _seed(request.seed, strip_params)
    scope = scope_rules(
        seed,
        scope=crawl_settings.scope,
        include=_patterns(crawl_settings.include, "include"),
        exclude=_patterns(crawl_settings.exclude, "exclude"),
    )
    if scope.folder == "/":
        raise _subfolder_is_root(seed)
    decision = scope.decide(seed)
    if not decision.in_scope:
        raise _seed_out_of_scope(seed, decision)
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
        scope=scope.to_json(),
        secret_names=request.secret_names,
        journal_setting=settings.table(StoreSettings).journal_mode,
        settings_file=settings_file,
        section_crawl=scope.section_crawl,
    )
    return CrawlPlan(
        seed=seed,
        settings=crawl_settings,
        scope=scope,
        strip_params=strip_params,
        new_crawl=new_crawl,
    )


def _seed(text: str, strip_params: re.Pattern[str] | None) -> NormalizedUrl:
    seed = parse_seed(text, strip_params)
    if isinstance(seed, InvalidUrl):
        raise _invalid_seed(text, seed.reason)
    return seed


def _patterns(texts: Sequence[str], key: str) -> tuple[re.Pattern[str], ...]:
    patterns = []
    for text in texts:
        try:
            patterns.append(re.compile(text))
        except re.error as error:
            raise SpiderError(
                INVALID_PATTERN,
                f"The pattern {text} is not a valid regular expression: {error}.",
                hint=f"Fix it in --{key} or in {key} of the settings file's [crawl] table: "
                "a Python regular expression, with a literal character such as ( or ? escaped.",
                details={"pattern": text},
            ) from None
    return tuple(patterns)


def start_crawl(
    plan: CrawlPlan,
    clock: Clock,
    reporter: Reporter,
    hooks: Hooks,
    *,
    resolver: AbstractResolver | None = None,
    pages: Callable[[], PageExecutor] | None = None,
    fetcher: Fetcher | None = None,
) -> CrawlResult:
    """`resolver` is the DNS resolver hook of multi-host tests, `pages` builds the page
    executor instead of `default_page_executor`, and `fetcher` is the fake Fetcher of the
    timing scenarios, used instead of aiohttp's (design D9, D15)."""
    log = WarningLog(reporter)
    crawl = _Crawl(
        plan=plan,
        crawl_file=create_crawl(plan.new_crawl, clock, log),
        clock=clock,
        log=log,
        hooks=hooks,
        resolver=resolver,
        pages=pages or default_page_executor,
        fetcher=fetcher,
    )
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        ended_at, summary, counts = runner.run(_run(crawl))
    return CrawlResult(
        crawl_id=crawl.crawl_file.id,
        summary=summary,
        ended_at=ended_at,
        counts=counts,
        crawl_file=crawl.crawl_file.path,
        warnings=log.warnings,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Crawl:
    """What start_crawl was given for one Crawl, with its new file and its warning log."""

    plan: CrawlPlan
    crawl_file: CrawlFile
    clock: Clock
    log: WarningLog
    hooks: Hooks
    resolver: AbstractResolver | None
    pages: Callable[[], PageExecutor]
    fetcher: Fetcher | None


async def _run(crawl: _Crawl) -> tuple[datetime, CrawlSummary, UrlCounts]:
    async with _crawl_context(crawl) as context:
        await run_crawl(context, crawl.plan.seed)
        stop_reason = context.stop.reason
        if stop_reason not in (None, "max_urls"):
            # Neither a write failure nor an interrupt has the end it records yet.
            raise context.stop.cause or RuntimeError(f"no end is built for {stop_reason}")
        writer = context.writer
        # Before the end is written, for completed and stopped alike: 040 reads either state as
        # "its Issues are materialised".
        for crawl_pass in crawl.hooks.passes:
            await crawl_pass.run(PassContext(writer, crawl.clock))
        # One instant: the result's ended_at is the time the file records for the end.
        ended_at = crawl.clock.now()
        state: CrawlState = "completed" if stop_reason is None else "stopped"
        await writer.run_async(record_state(state, ended_at, stop_reason))
        summary = await writer.run_async(crawl_summary())
        return ended_at, summary, await writer.run_async(url_counts())


@asynccontextmanager
async def _crawl_context(crawl: _Crawl) -> AsyncIterator[CrawlContext]:
    """The one place a Crawl's context is built, and its resources closed (design D15)."""
    plan, crawl_file, clock = crawl.plan, crawl.crawl_file, crawl.clock
    # Built before crawl_started reports its workers: nothing spawns before its start.
    executor = crawl.pages()
    try:
        crawl.log.event(
            "crawl_started",
            crawl_id=crawl_file.id,
            crawl_mode=plan.new_crawl.crawl_mode,
            seed_count=len(plan.new_crawl.seeds),
            crawl_file=str(crawl_file.path),
            parse_workers=executor.workers,
        )
        # Opening and closing the writer block, so they run off the event loop.
        with clock.off_loop():
            writer = await asyncio.to_thread(CrawlWriter, crawl_file.path, clock)
        try:
            fetching = (
                aiohttp_fetcher(clock, crawl.resolver)
                if crawl.fetcher is None
                else nullcontext(crawl.fetcher)
            )
            # The engine drives the writer, so its commits keep the Crawl's clock.
            async with writer.loop_deadline(), fetching as fetcher:
                yield CrawlContext(
                    crawl_file=crawl_file,
                    settings=plan.settings,
                    scope=plan.scope,
                    strip_params=plan.strip_params,
                    clock=clock,
                    reporter=crawl.log,
                    writer=writer,
                    fetcher=fetcher,
                    pages=executor,
                    hooks=crawl.hooks,
                    stop=StopSignal(),
                )
        except BaseException:
            # An ended writer raises why it ended once more; the error raised says it first.
            with suppress(CrawlWriterClosedError):
                await writer.close_async()
            raise
        await writer.close_async()
    finally:
        # 026's pool shuts its workers down here, however the Crawl ended.
        await executor.close()


def _seed_out_of_scope(seed: NormalizedUrl, decision: ScopeDecision) -> SpiderError:
    # A Seed is always internal and inside its own folder: only the patterns leave it out.
    why = (
        "it matches an --exclude pattern"
        if decision.skip_reason == "excluded"
        else "it matches no --include pattern"
    )
    return SpiderError(
        SEED_OUT_OF_SCOPE,
        f"The Seed {seed} is outside the Scope: {why}, so nothing would be crawled.",
        hint="Change the patterns, or give a Seed that the Scope holds.",
        details={"seed": seed},
    )


def _subfolder_is_root(seed: NormalizedUrl) -> SpiderError:
    path = url_path(seed)
    suggested: str | None = None
    if path == "/":
        hint = (
            f"Give a Seed inside a folder, such as {url_origin(seed)}/blog/, or leave out "
            "--scope subfolder to crawl the whole site."
        )
    else:
        suggested = f"{url_origin(seed)}{path}/"
        hint = f"Give {suggested} as the Seed, the folder's URL with its trailing slash."
    return SpiderError(
        SUBFOLDER_IS_ROOT,
        f"The folder of the Seed {seed} is the root, so --scope subfolder would crawl the "
        "whole site.",
        hint=hint,
        details={"seed": seed, "suggested_seed": suggested},
    )


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
