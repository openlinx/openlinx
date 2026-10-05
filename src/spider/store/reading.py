"""Reading crawl files read-only, one engine per operation (design D2 of 015-add-crawl-store)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, select
from sqlalchemy.pool import NullPool

from spider.store.schema import crawl


@contextmanager
def reading(path: Path) -> Iterator[Connection]:
    # as_uri() percent-encodes spaces, #, ?, % and non-ASCII names, which a URI must not hold raw.
    uri = f"{path.resolve().as_uri()}?mode=ro"
    engine = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(uri, uri=True), poolclass=NullPool
    )
    # Disposed at once, so no handle outlives the operation: Windows could not delete the file.
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def read_metadata(path: Path) -> dict[str, Any]:
    with reading(path) as connection:
        return dict(connection.execute(select(crawl)).mappings().one())
