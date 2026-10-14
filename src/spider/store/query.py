"""The reads of the query Commands (050-add-query-and-segments D14; data access stays in the
store, 020-add-crawl-core D14)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, case, select

from spider.rules.model import Rule
from spider.store.issues import issues_in


def ordered_issues(connection: Connection, catalogue: Sequence[Rule]) -> list[dict[str, Any]]:
    """The Issues by Issue Type, Priority, affected_count descending, then rule id."""
    found = issues_in(connection, catalogue).subquery()
    ordered = select(found).order_by(
        case({"issue": 0, "warning": 1, "opportunity": 2}, value=found.c.issue_type),
        case({"high": 0, "medium": 1, "low": 2}, value=found.c.priority),
        found.c.affected_count.desc(),
        found.c.rule_id,
    )
    return [dict(row._mapping) for row in connection.execute(ordered)]
