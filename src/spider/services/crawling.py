"""The Crawl Service: a foreground Spider-mode Crawl (020-add-crawl-core D11, D15)."""

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

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
from spider.services.crawl_failures import NETWORK_FAILURES, interrupted, write_failed
from spider.services.crawls import create_crawl
from spider.services.hooks import default_page_executor
from spider.services.interrupts import interrupts_stop
from spider.store.crawls import (
    crawl_summary,
    read_recorded,
    record_continue,
    record_state,
    record_warnings,
)
from spider.store.failures import is_write_failure
from spider.store.records import (
    CrawlFile,
    CrawlMode,
    CrawlState,
    CrawlSummary,
    NewCrawl,
    SecretNames,
    StopReason,
    UrlCounts,
)
from spider.store.settings import StoreSettings
from spider.store.transitions import check_transition
from spider.store.urls import url_counts
from spider.store.writer import CrawlWriter
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


class Recorded(Enum):
    KEEP = "keep"


# An override left out: the continue runs with the recorded value.
KEEP = Recorded.KEEP


@dataclass(frozen=True, slots=True, kw_only=True)
class CrawlOverrides:
    """The settings a continue may change, as 060 D8 lets a resume change them; 060 checks
    that a URL limit is only raised (design D20)."""

    max_urls: int | Literal[Recorded.KEEP] | None = KEEP
    concurrency: int | Literal[Recorded.KEEP] = KEEP
    rate: float | Literal[Recorded.KEEP] | None = KEEP

    def given(self) -> dict[str, Any]:
        values = {field.name: getattr(self, field.name) for field in fields(self)}
        return {name: value for name, value in values.items() if value is not KEEP}


@dataclass(frozen=True, kw_only=True)
class CrawlResult:
    """Built at the end from the crawl file, never from counters kept while it ran (D10)."""

    crawl_id: str
    summary: CrawlSummary
    ended_at: datetime
    counts: UrlCounts
    crawl_file: Path
    warnings: tuple[Diagnostic, ...]
    # The error of a failed Crawl, which the Command ends with after printing the result.
    failure: SpiderError | None = None

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
    stop: StopSignal | None = None,
) -> CrawlResult:
    """`resolver` is the DNS resolver hook of multi-host tests, `pages` builds the page
    executor instead of `default_page_executor`, `fetcher` is the fake Fetcher of the timing
    scenarios, used instead of aiohttp's, and `stop` is the stop flag that `060`'s control rows
    set (design D9, D10, D15)."""
    log = WarningLog(reporter)
    planned = _Planned(
        seed=plan.seed,
        settings=plan.settings,
        scope=plan.scope,
        strip_params=plan.strip_params,
        crawl_mode=plan.new_crawl.crawl_mode,
        seed_count=len(plan.new_crawl.seeds),
    )
    crawl = _Crawl(
        plan=planned,
        crawl_file=create_crawl(plan.new_crawl, clock, log),
        continuing=None,
        clock=clock,
        log=log,
        hooks=hooks,
        resolver=resolver,
        pages=pages or default_page_executor,
        fetcher=fetcher,
        stop=stop or StopSignal(),
    )
    return _crawled(crawl)


def continue_crawl(
    crawl_file: CrawlFile,
    overrides: CrawlOverrides,
    clock: Clock,
    reporter: Reporter,
    hooks: Hooks,
    *,
    resolver: AbstractResolver | None = None,
    pages: Callable[[], PageExecutor] | None = None,
    fetcher: Fetcher | None = None,
    stop: StopSignal | None = None,
) -> CrawlResult:
    """Continues a stopped or failed Crawl from its file alone, which 060's resume calls; the
    keyword arguments are start_crawl's (design D20)."""
    recorded = read_recorded(crawl_file.path)
    # Before anything is written; the continue's unit checks it again as it writes.
    check_transition(recorded.state, "running", None)
    settings = CrawlSettings.model_validate({**recorded.config["crawl"], **overrides.given()})
    strip_params = strip_params_pattern(settings.strip_params)
    planned = _Planned(
        seed=_seed(recorded.seeds[0], strip_params),
        settings=settings,
        scope=ScopeRules.from_json(recorded.scope),
        strip_params=strip_params,
        crawl_mode=recorded.crawl_mode,
        seed_count=len(recorded.seeds),
    )
    config = {**recorded.config, "crawl": settings.model_dump(mode="json")}
    crawl = _Crawl(
        plan=planned,
        crawl_file=crawl_file,
        continuing=config,
        clock=clock,
        log=WarningLog(reporter, [_diagnostic(w) for w in recorded.warnings]),
        hooks=hooks,
        resolver=resolver,
        pages=pages or default_page_executor,
        fetcher=fetcher,
        stop=stop or StopSignal(),
    )
    return _crawled(crawl)


def _diagnostic(stored: Mapping[str, Any]) -> Diagnostic:
    """A warning as crawl.warnings holds it, in the full diagnostic shape (design D10)."""
    return Diagnostic(
        stored["level"], stored["code"], stored["message"], stored["hint"], stored["details"]
    )


def _crawled(crawl: "_Crawl") -> CrawlResult:
    log = crawl.log
    # Before the loop runs: an interrupt's stop is set on the loop, and may come first.
    crawl.stop.on_first_set(
        lambda reason: log.event("stopping", crawl_id=crawl.crawl_file.id, reason=reason)
    )
    with (
        asyncio.Runner(loop_factory=loop_factory) as runner,
        interrupts_stop(runner.get_loop(), crawl.stop),
    ):
        ended = runner.run(_run(crawl))
    return CrawlResult(
        crawl_id=crawl.crawl_file.id,
        summary=ended.summary,
        ended_at=ended.ended_at,
        counts=ended.counts,
        crawl_file=crawl.crawl_file.path,
        warnings=log.warnings,
        failure=ended.failure,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _End:
    ended_at: datetime
    summary: CrawlSummary
    counts: UrlCounts
    failure: SpiderError | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _Planned:
    """What a run crawls with: a start's plan, or what a continue read from the file."""

    seed: NormalizedUrl
    settings: CrawlSettings
    scope: ScopeRules
    strip_params: re.Pattern[str] | None
    crawl_mode: CrawlMode
    seed_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _Crawl:
    """What start_crawl or continue_crawl was given for one run, with its file and its warning
    log."""

    plan: _Planned
    crawl_file: CrawlFile
    # The crawl.config a continue runs with, which the run writes and flushes before it crawls
    # (design D20).
    continuing: Mapping[str, Any] | None
    clock: Clock
    log: WarningLog
    hooks: Hooks
    resolver: AbstractResolver | None
    pages: Callable[[], PageExecutor]
    fetcher: Fetcher | None
    stop: StopSignal


async def _run(crawl: _Crawl) -> _End:
    try:
        return await _crawl_and_end(crawl)
    except _WriteFailed as failed:
        cause = failed.cause
    except Exception as error:
        # Raised outside a URL's unit: by the Seed's record, a pass, the end's own writes or the
        # final commit. It outranks a network reason whose end it kept from being written.
        if not is_write_failure(error):
            raise
        cause = error
    return await _failed_end(crawl, write_failed(crawl.crawl_file, cause))


class _WriteFailed(Exception):
    """The stop flag's write_failed, raised out of the Crawl's context so that its writer
    closes before the fresh one opens."""

    def __init__(self, cause: BaseException | None) -> None:
        super().__init__()
        self.cause = cause


async def _crawl_and_end(crawl: _Crawl) -> _End:
    async with _crawl_context(crawl) as context:
        if crawl.continuing is not None:
            await context.writer.run_async(record_continue(crawl.continuing, crawl.clock.now()))
            await context.writer.flush_async()
        await run_crawl(context, crawl.plan.seed)
        stop = context.stop
        reason = stop.close()
        if reason == "write_failed":
            raise _WriteFailed(stop.cause)
        if reason is not None and reason in NETWORK_FAILURES:
            ended = await _end(crawl, context.writer, "failed", reason)
            failure = NETWORK_FAILURES[reason]
            plan = crawl.plan
            return replace(ended, failure=failure(plan.seed, plan.settings, crawl.crawl_file))
        elif reason not in (None, "max_urls", "interrupt"):
            # 060's stop request has no end it records yet.
            raise stop.cause or RuntimeError(f"no end is built for {reason}")
        else:
            # Before the end is written, for completed and stopped alike: 040 reads either
            # state as "its Issues are materialised".
            for crawl_pass in crawl.hooks.passes:
                await crawl_pass.run(PassContext(context.writer, crawl.clock))
            state: CrawlState = "completed" if reason is None else "stopped"
            ended = await _end(crawl, context.writer, state, reason)
            if reason == "interrupt":
                return replace(ended, failure=interrupted(crawl.crawl_file))
            return ended


async def _failed_end(crawl: _Crawl, error: SpiderError) -> _End:
    """Recorded once more through a fresh writer, since the Crawl's own one may have ended; if
    that fails too, the file stays running (design D16)."""
    try:
        with crawl.clock.off_loop():
            writer = await asyncio.to_thread(CrawlWriter, crawl.crawl_file.path, crawl.clock)
        try:
            async with writer.loop_deadline():
                ended = await _end(crawl, writer, "failed", "write_failed")
        finally:
            await writer.close_async()
    except Exception as again:
        raise error from again
    return replace(ended, failure=error)


async def _end(
    crawl: _Crawl, writer: CrawlWriter, state: CrawlState, stop_reason: StopReason | None
) -> _End:
    # One instant: the result's ended_at is the time the file records for the end.
    ended_at = crawl.clock.now()
    # Before the end, so a reader that sees the end sees every warning.
    await writer.run_async(record_warnings([w.to_json() for w in crawl.log.warnings]))
    await writer.run_async(record_state(state, ended_at, stop_reason))
    summary = await writer.run_async(crawl_summary())
    return _End(ended_at=ended_at, summary=summary, counts=await writer.run_async(url_counts()))


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
            crawl_mode=plan.crawl_mode,
            seed_count=plan.seed_count,
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
                    stop=crawl.stop,
                )
        except BaseException:
            # An ended writer raises why it ended once more; the error raised says it first.
            try:
                await writer.close_async()
            except Exception as again:
                if not is_write_failure(again):
                    raise
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
