"""Request a graceful stop and observe when the selected Crawl ends."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from openlinx.clock import Clock
from openlinx.output.codes import CRAWL_BUSY
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.records import CrawlFile, CrawlState, StopReason
from openlinx.workspace.discovery import resolve_workspace

DEFAULT_STOP_WAIT_SECONDS = 60
_POLL_SECONDS = 1.0


@dataclass(frozen=True, kw_only=True)
class StopRequest:
    cwd: Path
    home: Path
    workspace: Path | None
    crawl: str
    wait_seconds: int = DEFAULT_STOP_WAIT_SECONDS


@dataclass(frozen=True, kw_only=True)
class StopResult:
    crawl_id: str
    state: CrawlState
    stop_reason: StopReason | None
    stop_requested: bool


def request_stop(request: StopRequest, clock: Clock) -> StopResult:
    """Start the wait after commit, or return the state at commit for a zero wait."""
    from openlinx.store.control import write_control
    from openlinx.store.selection import resolve_crawl

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    selected = resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
    state, reason = write_control(selected, clock.now(), os.getpid())
    if state == "running" and request.wait_seconds > 0:
        state, reason = asyncio.run(_wait_for_stop(selected, request.wait_seconds, clock))
    return StopResult(
        crawl_id=selected.id,
        state=state,
        stop_reason=reason,
        stop_requested=state == "running",
    )


async def _wait_for_stop(
    selected: CrawlFile, seconds: int, clock: Clock
) -> tuple[CrawlState, StopReason | None]:
    from openlinx.store.control import read_stop_state

    started = clock.monotonic()
    # A timer can wake late. Only a snapshot observed within the wait budget counts.
    while clock.monotonic() - started <= seconds:
        try:
            state, reason = read_stop_state(selected)
            if state != "running" and clock.monotonic() - started <= seconds:
                return state, reason
        except OpenLinxError as error:
            if error.code != CRAWL_BUSY.code:
                raise

        elapsed = clock.monotonic() - started
        if elapsed >= seconds:
            break
        delay = _POLL_SECONDS if elapsed + _POLL_SECONDS <= seconds else seconds - elapsed
        await clock.sleep(delay)
    return "running", None
