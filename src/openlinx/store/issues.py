"""Evaluate catalogue Rules and materialise their Affected URLs in the Crawl."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import orjson
from sqlalchemy import (
    Connection,
    Integer,
    Subquery,
    Text,
    bindparam,
    delete,
    func,
    insert,
    literal,
    select,
    text,
    union_all,
)

from openlinx.rules.model import Rule
from openlinx.store.reading import reading
from openlinx.store.records import AffectedUrl, Issue
from openlinx.store.schema import affected_urls, rules
from openlinx.store.writer import Unit


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """Run the catalogue Rule's query through a read-only connection."""
    with reading(crawl_file) as connection:
        return _affected_urls(connection, rule)


def _found(rule: Rule) -> Subquery:
    sql = rule.reproduce_sql.replace(":", "\\:") + "\n"
    return text(sql).columns(url_id=Integer, detail=Text).subquery()


def _affected_urls(connection: Connection, rule: Rule) -> list[AffectedUrl]:
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in connection.execute(select(_found(rule)))
    ]


_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id).where(rules.c.enabled == 1)


def affected_urls_unit(rule: Rule) -> Unit[None]:
    """Replace one Rule's result atomically, including when its new result is empty."""
    # text() treats :name as a parameter even inside SQL literals. Preserve the catalogue
    # query verbatim and end a trailing line comment before SQLAlchemy closes the subquery.
    found = _found(rule)
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def replace_rows(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return replace_rows


def _enabled_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(connection.scalars(_ENABLED))


class _IssueWriter(Protocol):
    async def run_async[T](self, unit: Unit[T]) -> T: ...


async def materialise_issues(writer: _IssueWriter, units: Mapping[str, Unit[None]]) -> None:
    """Run the installed Rule units enabled by this Crawl's snapshot."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule_id, unit in units.items():
        if rule_id in enabled:
            await writer.run_async(unit)


def read_issues(crawl_file: Path, catalogue: tuple[Rule, ...]) -> list[Issue]:
    """The live Issues of a Crawl, in the shape of its issues view."""
    statements = [
        select(
            literal(position).label("catalogue_order"),
            rules.c.id,
            rules.c.category,
            rules.c.issue_type,
            rules.c.priority,
            select(func.count())
            .select_from(_found(rule))
            .scalar_subquery()
            .label("affected_count"),
        ).where(rules.c.id == rule.id, rules.c.enabled == 1)
        for position, rule in enumerate(catalogue)
    ]
    if not statements:
        return []
    live_issues = union_all(*statements).subquery()
    with reading(crawl_file) as connection:
        rows = connection.execute(select(live_issues).order_by(live_issues.c.catalogue_order)).all()
    return [
        Issue(
            rule_id=row.id,
            category=row.category,
            issue_type=row.issue_type,
            priority=row.priority,
            affected_count=row.affected_count,
        )
        for row in rows
        if row.affected_count
    ]


def read_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: tuple[Rule, ...]
) -> list[AffectedUrl]:
    """The live Affected URLs of one Rule, ordered by URL id."""
    rule = next(rule for rule in catalogue if rule.id == rule_id)
    with reading(crawl_file) as connection:
        found = _affected_urls(connection, rule)
    return sorted(found, key=lambda url: url.url_id)
