"""The row writer of the links table, and the inlink pass's units (030-add-page-data D4, D6)."""

from collections.abc import Sequence
from dataclasses import fields

from sqlalchemy import Connection, bindparam, case, distinct, func, insert, select, update

from openlinx.store.page_records import LinkRow
from openlinx.store.schema import links, pages, urls

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


# About 10k Pages per unit, so no unit holds the writer long (030-add-page-data D6).
_RANGE = 10_000
_SOURCE = pages.alias("source")
_PAGES_200 = select(func.count()).where(pages.c.status_code == 200).scalar_subquery()
_INLINKS = (
    select(
        links.c.target_url_id.label("url_id"),
        func.count().label("inlinks"),
        func.count(distinct(links.c.source_url_id)).label("unique_inlinks"),
        func.count(distinct(case((_SOURCE.c.status_code == 200, links.c.source_url_id)))).label(
            "sources_200"
        ),
    )
    .select_from(links.join(_SOURCE, _SOURCE.c.url_id == links.c.source_url_id))
    .where(
        links.c.type == "hyperlink",
        links.c.target_url_id != links.c.source_url_id,
        links.c.target_url_id.between(bindparam("first"), bindparam("last")),
    )
    .group_by(links.c.target_url_id)
    .subquery()
)
_COUNTS = (
    select(
        pages.c.url_id,
        func.coalesce(_INLINKS.c.inlinks, 0).label("inlinks"),
        func.coalesce(_INLINKS.c.unique_inlinks, 0).label("unique_inlinks"),
        # Integer arithmetic, so the quotient is rounded half up exactly, not as a double.
        case(
            (_PAGES_200 == 0, None),
            else_=(20_000 * func.coalesce(_INLINKS.c.sources_200, 0) + _PAGES_200)
            // (2 * _PAGES_200)
            / 100.0,
        ).label("linking_pages_pct"),
    )
    .select_from(pages.outerjoin(_INLINKS, _INLINKS.c.url_id == pages.c.url_id))
    .where(pages.c.url_id.between(bindparam("first"), bindparam("last")))
    .subquery()
)
_UPDATE_INLINKS = (
    update(pages)
    .where(pages.c.url_id == _COUNTS.c.url_id)
    .values(
        inlinks=_COUNTS.c.inlinks,
        unique_inlinks=_COUNTS.c.unique_inlinks,
        linking_pages_pct=_COUNTS.c.linking_pages_pct,
    )
)
_PAGE_IDS = select(func.min(pages.c.url_id), func.max(pages.c.url_id))


def inlink_ranges(connection: Connection) -> list[tuple[int, int]]:
    """The url_id ranges of the inlink pass's units, first and last included."""
    first, last = connection.execute(_PAGE_IDS).one()
    if first is None:
        return []
    return [(start, min(start + _RANGE - 1, last)) for start in range(first, last + 1, _RANGE)]


def write_inlinks(first: int, last: int, connection: Connection) -> None:
    """Every inlink column of the Pages in the range, 0 included, so a rerun replaces them."""
    connection.execute(_UPDATE_INLINKS, {"first": first, "last": last})
