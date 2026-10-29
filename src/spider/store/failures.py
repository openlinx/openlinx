"""Which write failures are one URL's, and which the crawl file's (020-add-crawl-core D2, D16)."""

import sqlite3

from sqlalchemy.exc import DBAPIError

from spider.output.codes import CRAWL_BUSY
from spider.output.diagnostics import SpiderError
from spider.store.writer import CrawlWriterClosedError, CrawlWriterReplayError

# A value the file refuses: a constraint, a value too big, a value that cannot be bound.
_ONE_ROW = (sqlite3.IntegrityError, sqlite3.DataError, sqlite3.InterfaceError)


def is_write_failure(error: BaseException) -> bool:
    """True when writing the crawl file failed, wherever it was written: the writer ended or
    its replay failed, another connection held the file, or the database refused for a reason
    that is not one row's (020-add-crawl-core D16)."""
    # The writer's own errors first: none of them is a database error.
    if isinstance(error, CrawlWriterClosedError | CrawlWriterReplayError):
        return True
    if isinstance(error, SpiderError) and error.code == CRAWL_BUSY.code:
        return True
    cause = _database_error(error)
    return isinstance(cause, sqlite3.Error) and not isinstance(cause, _ONE_ROW)


def write_failure_cause(error: BaseException) -> BaseException:
    """The error the write failed on: an ended writer refuses with the error it ended on as
    its cause (017 D6)."""
    if isinstance(error, CrawlWriterClosedError) and error.__cause__ is not None:
        return error.__cause__
    return error


def is_one_urls_failure(error: BaseException) -> bool:
    """True when the URL alone failed, so a fallback unit records it; else the file failed."""
    # A row the file refuses, or our own row code's error: one row's.
    return not is_write_failure(error) and isinstance(_database_error(error), Exception)


def _database_error(error: BaseException) -> BaseException | None:
    return error.orig if isinstance(error, DBAPIError) else error
