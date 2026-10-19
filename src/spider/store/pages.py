"""The row writers of the pages and cookies tables (030-add-page-data D1)."""

from dataclasses import fields

from sqlalchemy import Connection, bindparam, insert, select

from spider.store.page_records import CookieRow, PageRow
from spider.store.schema import cookies, pages, urls

# Built once: it runs once per Page (017-speed-up-crawl-writer D9).
# The depth is read in the Page's unit: a late check may have lowered it while the URL was in
# flight, after the engine handed the URL out.
_INSERT_PAGE = insert(pages).values(
    crawl_depth=select(urls.c.crawl_depth)
    .where(urls.c.id == bindparam("depth_of"))
    .scalar_subquery()
)
_COLUMNS = tuple(field.name for field in fields(PageRow))
_INSERT_COOKIE = insert(cookies)
_COOKIE_COLUMNS = tuple(field.name for field in fields(CookieRow))


def write_page(connection: Connection, row: PageRow) -> None:
    connection.execute(
        _INSERT_PAGE,
        {"depth_of": row.url_id, **{name: getattr(row, name) for name in _COLUMNS}},
    )


def write_cookie(connection: Connection, row: CookieRow) -> None:
    connection.execute(_INSERT_COOKIE, {name: getattr(row, name) for name in _COOKIE_COLUMNS})
