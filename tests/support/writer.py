"""Driving the crawl writer in tests (design D7 of 017-speed-up-crawl-writer)."""

from collections.abc import Callable
from contextlib import suppress

from sqlalchemy import Connection, Executable

from spider.store.writer import CrawlWriter


def executing(statement: Executable) -> Callable[[Connection], None]:
    """A unit that runs one statement and returns None, not SQLAlchemy's result (design D7)."""

    def unit(connection: Connection) -> None:
        connection.execute(statement)

    return unit


class _ReplayNow(Exception):
    pass


def replay_now(writer: CrawlWriter) -> None:
    """Makes the writer run every unit since the last commit again, as a failing unit does."""

    def fail(connection: Connection) -> None:
        raise _ReplayNow

    with suppress(_ReplayNow):
        writer.run(fail)
    # A unit that ran again differently has ended the writer: fail here, at its cause.
    writer.flush()
