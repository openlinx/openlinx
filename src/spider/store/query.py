"""The reads of the query Commands (050-add-query-and-segments D14, 020-add-crawl-core D14)."""

from collections.abc import Sequence
from typing import Any

import orjson
from sqlalchemy import Connection, bindparam, case, func, select

from spider.rules.model import Rule
from spider.store.issues import affected_urls_in, decode_detail, issues_in
from spider.store.records import IssueFilters, IssueType, Priority
from spider.store.schema import literal_values, rules, urls

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
# The Issue list's order is the order in which the types declare their values.
_ISSUE_TYPE_PLACES = {value: place for place, value in enumerate(literal_values(IssueType))}
_PRIORITY_PLACES = {value: place for place, value in enumerate(literal_values(Priority))}


def ordered_issues(
    connection: Connection, catalogue: Sequence[Rule], filters: IssueFilters
) -> list[dict[str, Any]]:
    """The Issues that pass `filters`, with their Rules' descriptions from the Crawl's rules
    table, by Issue Type, Priority, affected_count descending, then rule id."""
    found = issues_in(connection, catalogue).subquery()
    accepted = [
        column.in_(values)
        for column, values in (
            (found.c.issue_type, filters.issue_types),
            (found.c.priority, filters.priorities),
            (found.c.category, filters.categories),
        )
        if values
    ]
    ordered = (
        select(found, rules.c.description)
        .join_from(found, rules, rules.c.id == found.c.rule_id)
        .where(*accepted)
        .order_by(
            case(_ISSUE_TYPE_PLACES, value=found.c.issue_type),
            case(_PRIORITY_PLACES, value=found.c.priority),
            found.c.affected_count.desc(),
            found.c.rule_id,
        )
    )
    return [dict(row._mapping) for row in connection.execute(ordered)]


def affected_url_page(
    connection: Connection,
    rule_id: str,
    catalogue: Sequence[Rule],
    *,
    after: str | None,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    """The number of the Rule's Affected URLs, and at most `limit` of them as {url, detail},
    in URL order after the URL `after`: a keyset page, which never repeats a URL of an earlier
    page, though finding it sorts all the Issue's rows (design D4, D15)."""
    # One select for both reads: the reader chooses the stored or the live path once.
    found = affected_urls_in(connection, rule_id, catalogue).subquery()
    total: int = connection.execute(select(func.count()).select_from(found)).scalar_one()
    ordered = (
        select(urls.c.url, found.c.detail)
        .join_from(found, urls, urls.c.id == found.c.url_id)
        .where(*([] if after is None else [urls.c.url > after]))
        .order_by(urls.c.url)
        .limit(limit)
    )
    return total, [
        {"url": url, "detail": decode_detail(detail)} for url, detail in connection.execute(ordered)
    ]


def recorded_rule(connection: Connection, rule_id: str) -> dict[str, Any]:
    """The Rule as the Crawl's rules table records it, with the thresholds that applied."""
    row = connection.execute(_RULE, {"rule_id": rule_id}).one()
    return {**row._asdict(), "thresholds": orjson.loads(row.thresholds)}
