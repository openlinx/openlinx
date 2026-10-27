"""The Health Score: its formula, its counts over stored rows, and the pass's unit that writes it
on the crawl row (040-add-rules D8)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Select, distinct, func, select, update

from spider.store.issues import STORED_AFFECTED_URLS
from spider.store.records import Health
from spider.store.schema import crawl, pages, rules

# Every Internal Page: the url_id that the Crawl's Health Score rates.
INTERNAL_PAGES = select(pages.c.url_id)
_ISSUE_RULES = select(rules.c.id).where(rules.c.issue_type == "issue", rules.c.enabled == 1)


def health_score(internal_pages: int, affected_pages: int) -> int | None:
    if not internal_pages:
        return None
    # Rounded down, so 100 means that no Page has an Issue-type Issue.
    return 100 * (internal_pages - affected_pages) // internal_pages


def health(connection: Connection, rated: Select[Any], affected: Select[Any]) -> Health:
    """The Health Score of the Pages among the url_id that `rated` selects, counted against the
    Affected URLs, rule_id and url_id, that `affected` selects, of an enabled Issue-type Rule."""
    # Only Pages count: a Segment of URLs also holds URLs that are no Page.
    rated_pages = select(pages.c.url_id).where(
        pages.c.url_id.in_(select(rated.subquery().c.url_id))
    )
    found = affected.subquery()
    counted = select(
        select(func.count()).select_from(rated_pages.subquery()).scalar_subquery(),
        select(func.count(distinct(found.c.url_id)))
        .where(found.c.url_id.in_(rated_pages), found.c.rule_id.in_(_ISSUE_RULES))
        .scalar_subquery(),
    )
    internal, affected_pages = connection.execute(counted).one()
    return Health(
        score=health_score(internal, affected_pages),
        internal_pages=internal,
        affected_pages=affected_pages,
    )


def health_unit(calculated_at: datetime) -> Callable[[Connection], None]:
    """The pass's last unit: the Crawl's Health Score over the stored Affected URLs, on the crawl
    row."""

    def unit(connection: Connection) -> None:
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)
        connection.execute(
            update(crawl).values(
                health_score=found.score,
                health_internal_page_count=found.internal_pages,
                health_affected_page_count=found.affected_pages,
                health_calculated_at=calculated_at,
            )
        )

    return unit
