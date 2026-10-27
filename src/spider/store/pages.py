"""The row writer of the pages table (030-add-page-data D1)."""

from collections.abc import Sequence
from dataclasses import fields

from sqlalchemy import Connection, insert

from spider.store.page_records import PageRow
from spider.store.schema import pages

# Built once: it runs once per Page (017-speed-up-crawl-writer D9).
_INSERT_PAGE = insert(pages)
_COLUMNS = tuple(field.name for field in fields(PageRow))


def write_pages(connection: Connection, rows: Sequence[PageRow]) -> None:
    connection.execute(
        _INSERT_PAGE, [{name: getattr(row, name) for name in _COLUMNS} for row in rows]
    )
