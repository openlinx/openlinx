"""The row writer of the pages table (030-add-page-data D1)."""

from dataclasses import asdict

from sqlalchemy import Connection, insert

from spider.store.page_records import PageRow
from spider.store.schema import pages

# Built once: it runs once per Page (017-speed-up-crawl-writer D9).
_INSERT_PAGE = insert(pages)


def write_page(connection: Connection, row: PageRow) -> None:
    connection.execute(_INSERT_PAGE, asdict(row))
