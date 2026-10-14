"""Which failures of a URL's unit are that URL's alone (020-add-crawl-core D2)."""

import sqlite3

from sqlalchemy.exc import DBAPIError

from spider.output.codes import CRAWL_BUSY
from spider.output.diagnostics import SpiderError
from spider.store.writer import CrawlWriterClosedError, CrawlWriterReplayError

# A value the file refuses: a constraint, a value too big, a value that cannot be bound.
_ONE_ROW = (sqlite3.IntegrityError, sqlite3.DataError, sqlite3.InterfaceError)


def is_one_rows_error(error: BaseException) -> bool:
    """True when the URL alone failed, so a fallback unit records it; else the file failed."""
    # The writer's own errors first: none of them is a database error.
    if isinstance(error, CrawlWriterClosedError | CrawlWriterReplayError):
        return False
    if isinstance(error, SpiderError) and error.code == CRAWL_BUSY.code:
        return False
    cause = error.orig if isinstance(error, DBAPIError) else error
    if isinstance(cause, _ONE_ROW):
        return True
    # Every other database error is the file's or the connection's; our row code's are one row's.
    return isinstance(cause, Exception) and not isinstance(cause, sqlite3.Error)
