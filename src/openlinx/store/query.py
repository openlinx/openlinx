"""Read the Issue list in the order used by the Query Service."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, case, select

from openlinx.store.crawls import check_rule_tables
from openlinx.store.issues import issues_in
from openlinx.store.rule_queries import RuleQuery
from openlinx.store.schema import rules


def ordered_issues_in(
    connection: Connection,
    path: Path,
    catalogue: Sequence[RuleQuery],
    *,
    issue_types: tuple[str, ...] = (),
    priorities: tuple[str, ...] = (),
    categories: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Join the reader's Issues to the Rule descriptions recorded for this Crawl."""
    check_rule_tables(connection, path)
    source = issues_in(connection, catalogue).subquery()
    statement = (
        select(source, rules.c.description)
        .join_from(source, rules, rules.c.id == source.c.rule_id)
        .order_by(
            case({"issue": 0, "warning": 1, "opportunity": 2}, value=source.c.issue_type),
            case({"high": 0, "medium": 1, "low": 2}, value=source.c.priority),
            source.c.affected_count.desc(),
            source.c.rule_id,
        )
    )
    if issue_types:
        statement = statement.where(source.c.issue_type.in_(issue_types))
    if priorities:
        statement = statement.where(source.c.priority.in_(priorities))
    if categories:
        statement = statement.where(source.c.category.in_(categories))
    return [
        {str(key): value for key, value in row.items()}
        for row in connection.execute(statement).mappings()
    ]
