"""Observe committed control requests on the Crawl's Clock."""

import asyncio
from datetime import datetime

from openlinx.clock import Clock
from openlinx.crawl.engine.stop import StopSignal
from openlinx.output.codes import CRAWL_BUSY
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.control import pending_stop_request
from openlinx.store.records import CrawlFile

_STOP_CHECK_SECONDS = 1.0


async def watch_stop_requests(
    selected: CrawlFile, after: int, clock: Clock, stop: StopSignal
) -> tuple[int, datetime] | None:
    """Keep each short SQLite snapshot off the Crawl's loop and outside writer replay."""
    tick = clock.monotonic() + _STOP_CHECK_SECONDS
    while True:
        await clock.sleep(max(0.0, tick - clock.monotonic()))
        tick = clock.monotonic() + _STOP_CHECK_SECONDS
        try:
            with clock.off_loop():
                request = await asyncio.to_thread(pending_stop_request, selected, after=after)
        except OpenLinxError as error:
            if error.code != CRAWL_BUSY.code:
                raise
        else:
            if request is not None:
                at = clock.now()
                return (request, at) if stop.request_from_store() else None
