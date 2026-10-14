"""The reads of the query Commands (050-add-query-and-segments D14; data access stays in the
store, 020-add-crawl-core D14)."""

from collections.abc import Collection, Sequence
from typing import Any

import orjson
from sqlalchemy import Connection, bindparam, case, func, select

from spider.rules.model import Rule
from spider.store.issues import affected_urls_in, issues_in
from spider.store.schema import rules, urls

_RULE = select(
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


def affected_url_items(
    connection: Connection,
    rule_id: str,
    catalogue: Sequence[Rule],
    *,
    after: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """At most `limit` of the Rule's Affected URLs as {url, detail}, in URL order, after the
    URL `after`: a keyset page, which reads only its rows of the ordered URLs (design D4)."""
    found = affected_urls_in(connection, rule_id, catalogue).subquery()
    ordered = (
        select(urls.c.url, found.c.detail)
        .join_from(found, urls, urls.c.id == found.c.url_id)
        .where(*([] if after is None else [urls.c.url > after]))
        .order_by(urls.c.url)
        .limit(limit)
    )
    return [
        {"url": url, "detail": None if detail is None else orjson.loads(detail)}
        for url, detail in connection.execute(ordered)
    ]


def recorded_rule(connection: Connection, rule_id: str) -> dict[str, Any]:
    """The Rule as the Crawl's rules table records it, with the thresholds that applied."""
    row = connection.execute(_RULE, {"rule_id": rule_id}).one()
    return {**row._asdict(), "thresholds": orjson.loads(row.thresholds)}


def affected_url_count(connection: Connection, rule_id: str, catalogue: Sequence[Rule]) -> int:
    found = affected_urls_in(connection, rule_id, catalogue).subquery()
    count: int = connection.execute(select(func.count()).select_from(found)).scalar_one()
    return count
