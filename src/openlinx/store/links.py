"""The row writer of the links table (030-add-page-data D4)."""

from collections.abc import Sequence
from dataclasses import fields

from sqlalchemy import Connection, bindparam, insert, select

from openlinx.store.page_records import LinkRow
from openlinx.store.schema import links, urls

# Built once: it runs once per URL (017-speed-up-crawl-writer D9). The target's id is read in
# the unit, which records the URLs its response discovered before the handlers' rows.
_INSERT_LINK = insert(links).values(
    target_url_id=select(urls.c.id).where(urls.c.url == bindparam("target")).scalar_subquery()
)
_COLUMNS = tuple(field.name for field in fields(LinkRow) if field.name != "target")


def write_links(connection: Connection, rows: Sequence[LinkRow]) -> None:
    connection.execute(
        _INSERT_LINK,
        [{"target": row.target, **{name: getattr(row, name) for name in _COLUMNS}} for row in rows],
    )
