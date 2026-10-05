"""Reading crawl files read-only, one engine per operation (design D2 of 015-add-crawl-store)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select
from sqlalchemy.exc import DBAPIError

from spider.output.codes import CRAWL_BUSY
from spider.output.diagnostics import SpiderError
from spider.store.connections import READER_BUSY_SECONDS, is_busy, opening
from spider.store.schema import crawl


@contextmanager
def reading(path: Path) -> Iterator[Connection]:
    try:
        with opening(path, read_only=True) as engine, engine.connect() as connection:
            yield connection
    except DBAPIError as error:
        if not is_busy(error):
            raise
        raise SpiderError(
            CRAWL_BUSY,
            f"The crawl file {path} is held by a write, and reading waited "
            f"{READER_BUSY_SECONDS:g} seconds.",
            hint="Try again when the write has ended.",
            details={"file": str(path)},
        ) from error


def read_metadata(path: Path) -> dict[str, Any]:
    with reading(path) as connection:
        return dict(connection.execute(select(crawl)).mappings().one())
