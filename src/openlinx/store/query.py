"""Read Issues and their recorded Rule metadata for the Query Service."""

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, bindparam, case, func, select

from openlinx.store.issues import affected_urls_in, decode_detail, issues_in
from openlinx.store.rule_queries import RuleQuery
from openlinx.store.schema import rules, urls

_RECORDED_RULE = select(
    rules.c.id.label("rule_id"),
    rules.c.category,
    rules.c.issue_type,
    rules.c.priority,
    rules.c.description,
    rules.c.why_it_matters,
    rules.c.how_to_fix,
    rules.c.thresholds,
    rules.c.reproduce_sql,
).where(rules.c.id == bindparam("rule_id"))


def ordered_issues_in(
    connection: Connection,
    catalogue: Sequence[RuleQuery],
    *,
    issue_types: tuple[str, ...] = (),
    priorities: tuple[str, ...] = (),
    categories: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Join the reader's Issues to the Rule descriptions recorded for this Crawl."""
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


def issue_detail_in(
    connection: Connection,
    rule_id: str,
    catalogue: Sequence[RuleQuery],
    *,
    after: str | None,
    limit: int,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Read the recorded Rule, total before paging, and at most limit Affected URLs."""
    # The Issues reader validates the recorded Rule id and selects the live or stored source.
    source = affected_urls_in(connection, rule_id, catalogue).subquery()
    total: int = connection.execute(select(func.count()).select_from(source)).scalar_one()
    statement = (
        select(urls.c.url, source.c.detail)
        .join_from(source, urls, urls.c.id == source.c.url_id)
        .order_by(urls.c.url)
        .limit(limit)
    )
    if after is not None:
        statement = statement.where(urls.c.url > after)
    items = [
        {"url": url, "detail": decode_detail(detail)}
        for url, detail in connection.execute(statement)
    ]
    row = connection.execute(_RECORDED_RULE, {"rule_id": rule_id}).mappings().one()
    header = {str(key): value for key, value in row.items()}
    # Recorded thresholds can exceed the range that orjson reads as exact integers.
    header["thresholds"] = json.loads(row["thresholds"])
    return header, total, items
