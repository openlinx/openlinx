"""Calculate and record the Health Score from Pages and recorded Rule results."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, Select, func, select, update
from sqlalchemy.sql import FromClause

from openlinx.store.preview import is_historical_preview, missing_health_columns
from openlinx.store.schema import affected_urls, crawl, pages, rules
from openlinx.store.writer import Unit


@dataclass(frozen=True, slots=True)
class Health:
    """A Health Score with the two Page counts used to calculate it."""

    score: int | None
    internal_pages: int
    affected_pages: int


def _counts(page_rows: FromClause, affected: FromClause) -> Select[int, int]:
    internal = select(func.count()).select_from(page_rows).scalar_subquery()
    affected_pages = (
        select(func.count(affected.c.url_id.distinct()))
        .select_from(
            affected.join(rules, rules.c.id == affected.c.rule_id).join(
                page_rows, page_rows.c.url_id == affected.c.url_id
            )
        )
        .where(rules.c.enabled == 1, rules.c.issue_type == "issue")
        .scalar_subquery()
    )
    return select(internal, affected_pages)


_MATERIALISED_COUNTS = _counts(pages, affected_urls)
_RECORD_HEALTH = update(crawl)


def health_score(internal_pages: int, affected_pages: int) -> int | None:
    """Return the floored score, or None for an empty population of Internal Pages."""
    if internal_pages == 0:
        return None
    return 100 * (internal_pages - affected_pages) // internal_pages


def _read_health(connection: Connection, statement: Select[int, int]) -> Health:
    internal, affected = connection.execute(statement).one()
    return Health(
        score=health_score(internal, affected),
        internal_pages=internal,
        affected_pages=affected,
    )


def materialised_health(connection: Connection) -> Health:
    """Calculate the Health Score from the last materialised Issues and current Pages."""
    return _read_health(connection, _MATERIALISED_COUNTS)


def record_health(calculated_at: datetime) -> Unit[None]:
    """Update the score and both counts together, with a timestamp fixed for writer replay."""

    def unit(connection: Connection) -> None:
        if is_historical_preview(connection, missing_health_columns(connection)):
            return
        result = materialised_health(connection)
        connection.execute(
            _RECORD_HEALTH,
            {
                "health_score": result.score,
                "health_internal_page_count": result.internal_pages,
                "health_affected_page_count": result.affected_pages,
                "health_calculated_at": calculated_at,
            },
        )

    return unit


def health_for_pages(
    connection: Connection, *, page_ids: Select[int], affected: FromClause = affected_urls
) -> Health:
    """Score the selected Internal Pages. A live source provides url_id and rule_id columns."""
    # Membership preserves one row per Page even if the selection joins one-to-many data.
    selected = select(pages.c.url_id).where(pages.c.url_id.in_(page_ids)).subquery()
    return _read_health(connection, _counts(selected, affected))
