"""Reading crawl files read-only, one engine per operation (design D2 of 015-add-crawl-store)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select

from spider.store.connections import opening
from spider.store.schema import crawl


@contextmanager
def reading(path: Path) -> Iterator[Connection]:
    with opening(path, read_only=True) as engine, engine.connect() as connection:
        yield connection


def read_metadata(path: Path) -> dict[str, Any]:
    with reading(path) as connection:
        return dict(connection.execute(select(crawl)).mappings().one())
