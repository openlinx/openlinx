"""Resolve a Crawl and present the committed Status snapshot."""

from pathlib import Path

import msgspec

from openlinx.store.records import CrawlMode, CrawlState, StopReason, UrlCounts
from openlinx.store.selection import resolve_crawl
from openlinx.store.status import read_status
from openlinx.workspace.discovery import resolve_workspace


class StatusUrls(msgspec.Struct, frozen=True, kw_only=True):
    discovered: int
    fetched: int
    errors: int
    skipped: int
    queued: int


class StatusClasses(msgspec.Struct, frozen=True, kw_only=True):
    status_2xx: int = msgspec.field(name="2xx")
    status_3xx: int = msgspec.field(name="3xx")
    status_4xx: int = msgspec.field(name="4xx")
    status_5xx: int = msgspec.field(name="5xx")
    other: int


class StatusResult(msgspec.Struct, frozen=True, kw_only=True):
    crawl_id: str
    state: CrawlState
    stop_reason: StopReason | None
    crawl_mode: CrawlMode
    seed: str | None
    seed_count: int
    section_crawl: bool
    started_at: str
    completed_at: str | None
    urls: StatusUrls | None
    status_classes: StatusClasses | None
    eta_s: int | None


def _status_counts(counts: UrlCounts | None) -> tuple[StatusUrls | None, StatusClasses | None]:
    if counts is None:
        return None, None
    return (
        StatusUrls(
            discovered=counts.discovered,
            fetched=counts.fetched,
            errors=counts.errors,
            skipped=counts.skipped,
            queued=counts.queued,
        ),
        StatusClasses(
            status_2xx=counts.status_2xx,
            status_3xx=counts.status_3xx,
            status_4xx=counts.status_4xx,
            status_5xx=counts.status_5xx,
            other=counts.status_other,
        ),
    )


def show_status(cwd: Path, home: Path, *, workspace_dir: Path | None, crawl: str) -> StatusResult:
    workspace = resolve_workspace(cwd=cwd, flag=workspace_dir, home=home)
    selected = resolve_crawl(crawl, workspace=workspace, cwd=cwd)
    snapshot = read_status(selected)
    summary = snapshot.summary
    urls, status_classes = _status_counts(snapshot.counts)
    return StatusResult(
        crawl_id=selected.id,
        state=summary.state,
        stop_reason=summary.stop_reason,
        crawl_mode=summary.crawl_mode,
        seed=summary.seed,
        seed_count=summary.seed_count,
        section_crawl=summary.section_crawl,
        started_at=summary.started_at,
        completed_at=snapshot.completed_at,
        urls=urls,
        status_classes=status_classes,
        eta_s=None,
    )
