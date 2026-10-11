"""Driving the crawl writer in tests (design D7 of 017-speed-up-crawl-writer)."""

from contextlib import suppress

from sqlalchemy import Connection

from spider.store.writer import CrawlWriter


class _ReplayNow(Exception):
    pass


def replay_now(writer: CrawlWriter) -> None:
    """Makes the writer run every unit since the last commit again, as a failing unit does."""

    def fail(connection: Connection) -> None:
        raise _ReplayNow

    with suppress(_ReplayNow):
        writer.run(fail)
