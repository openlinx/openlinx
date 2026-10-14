"""The reads of the query Commands (050-add-query-and-segments D14; data access stays in the
store, 020-add-crawl-core D14)."""

from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import Connection, case, select

from spider.rules.model import Rule
from spider.store.issues import issues_in
from spider.store.schema import rules


def ordered_issues(
    connection: Connection,
    catalogue: Sequence[Rule],
    *,
    issue_types: Collection[str] = (),
    priorities: Collection[str] = (),
    categories: Collection[str] = (),
) -> list[dict[str, Any]]:
    """The Issues with their Rules' descriptions, from the Crawl's rules table, by Issue Type,
    Priority, affected_count descending, then rule id; an empty filter accepts every value."""
    found = issues_in(connection, catalogue).subquery()
    accepted = [
        column.in_(values)
        for column, values in (
            (found.c.issue_type, issue_types),
            (found.c.priority, priorities),
            (found.c.category, categories),
        )
        if values
    ]
    ordered = (
        select(found, rules.c.description)
        .join_from(found, rules, rules.c.id == found.c.rule_id)
        .where(*accepted)
        .order_by(
            case({"issue": 0, "warning": 1, "opportunity": 2}, value=found.c.issue_type),
            case({"high": 0, "medium": 1, "low": 2}, value=found.c.priority),
            found.c.affected_count.desc(),
            found.c.rule_id,
        )
    )
    return [dict(row._mapping) for row in connection.execute(ordered)]
