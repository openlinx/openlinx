"""The row writers of the pages and cookies tables (030-add-page-data D1)."""

from dataclasses import fields

from sqlalchemy import Connection, insert

from spider.store.page_records import CookieRow, PageRow
from spider.store.schema import cookies, pages

# Built once: it runs once per Page (017-speed-up-crawl-writer D9).
_INSERT_PAGE = insert(pages)
_COLUMNS = tuple(field.name for field in fields(PageRow))
_INSERT_COOKIE = insert(cookies)
_COOKIE_COLUMNS = tuple(field.name for field in fields(CookieRow))


def write_page(connection: Connection, row: PageRow) -> None:
    connection.execute(_INSERT_PAGE, {name: getattr(row, name) for name in _COLUMNS})


def write_cookie(connection: Connection, row: CookieRow) -> None:
    connection.execute(_INSERT_COOKIE, {name: getattr(row, name) for name in _COOKIE_COLUMNS})
