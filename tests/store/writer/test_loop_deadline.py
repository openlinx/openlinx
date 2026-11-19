"""Verify sync admission and commit visibility under the Writer's event-loop deadline."""

import pytest
from sqlalchemy import Connection

from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_without_seeds, insert_seed, query
from tests.support.workspace import TempWorkspace

COUNT = "SELECT count(*) FROM seeds"


async def test_a_sync_submit_under_a_loop_s_commit_deadline_is_refused(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    ran: list[str] = []

    def inserting(connection: Connection) -> None:
        ran.append("insert")
        insert_seed(1, "https://example.com/a")(connection)

    writer = CrawlWriter(crawl.path, FakeClock())
    try:
        async with writer.loop_deadline():
            with pytest.raises(RuntimeError, match="inside a Crawl use submit_async / run_async"):
                writer.submit(inserting)
            with pytest.raises(RuntimeError, match="inside a Crawl use submit_async / run_async"):
                writer.run(inserting)
        refused = list(ran)
        # Released: the writer is a sync one again.
        writer.run(inserting)
    finally:
        await writer.close_async()

    assert (refused, ran, query(crawl.path, COUNT)) == ([], ["insert"], [(1,)])


async def test_a_unit_submitted_under_a_loop_s_commit_deadline_commits_at_the_deadline(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    clock = FakeClock()

    writer = CrawlWriter(crawl.path, clock)
    try:
        async with writer.loop_deadline():
            committed = await writer.submit_async(insert_seed(1, "https://example.com/a"))
            before = query(crawl.path, COUNT)
            await clock.sleep(1.0)
            await committed
            seen = (query(crawl.path, COUNT), clock.monotonic())
    finally:
        await writer.close_async()

    assert (before, seen) == ([(0,)], ([(1,)], 1.0))
