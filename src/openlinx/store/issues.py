"""Evaluate catalogue Rules and materialise their Affected URLs in the Crawl."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import orjson
from sqlalchemy import (
    Connection,
    Integer,
    Select,
    Subquery,
    Text,
    bindparam,
    case,
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
from openlinx.store.records import AffectedUrl, CrawlState, Issue
from openlinx.store.schema import affected_urls, crawl, issues, rules
from openlinx.store.writer import Unit


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """Run the catalogue Rule's query through a read-only connection."""
    with reading(crawl_file) as connection:
        return _affected_urls(connection, select(_found(rule)))


def _found(rule: Rule) -> Subquery:
    sql = rule.reproduce_sql.replace(":", "\\:") + "\n"
    return text(sql).columns(url_id=Integer, detail=Text).subquery()


def _affected_urls(connection: Connection, statement: Select[int, str | None]) -> list[AffectedUrl]:
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in connection.execute(statement)
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


_ISSUE_STATE = select(crawl.c.state)
_STORED_ISSUES = select(
    issues.c.rule_id.label("id"),
    issues.c.category,
    issues.c.issue_type,
    issues.c.priority,
    issues.c.affected_count,
)


@contextmanager
def _reading_issues(crawl_file: Path) -> Iterator[tuple[Connection, bool]]:
    with reading(crawl_file) as connection:
        # SQLite's legacy transaction mode does not start a transaction for SELECT.
        # A Writer may publish a new result and State between these two reads.
        connection.exec_driver_sql("BEGIN")
        state: CrawlState = connection.execute(_ISSUE_STATE).scalar_one()
        yield connection, state in ("completed", "stopped")


def _live_issues(catalogue: tuple[Rule, ...]) -> Select[str, str, str, str, int]:
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
    live = union_all(*statements).subquery()
    return select(
        live.c.id, live.c.category, live.c.issue_type, live.c.priority, live.c.affected_count
    ).order_by(live.c.catalogue_order)


def read_issues(crawl_file: Path, catalogue: tuple[Rule, ...]) -> list[Issue]:
    """The Issues from the final pass or from the enabled Rules over current rows."""
    with _reading_issues(crawl_file) as (connection, materialised):
        if materialised:
            order = {rule.id: position for position, rule in enumerate(catalogue)}
            statement = _STORED_ISSUES
            if order:
                statement = statement.order_by(
                    case(order, value=issues.c.rule_id, else_=len(order))
                )
            rows = connection.execute(statement.order_by(issues.c.rule_id)).all()
        elif catalogue:
            rows = connection.execute(_live_issues(catalogue)).all()
        else:
            return []

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
    """One Rule's Affected URLs from the final pass or current rows, ordered by URL id."""
    with _reading_issues(crawl_file) as (connection, materialised):
        if materialised:
            stored = select(affected_urls.c.url_id, affected_urls.c.detail).where(
                affected_urls.c.rule_id == rule_id
            )
            return _affected_urls(connection, stored.order_by(affected_urls.c.url_id))

        rule = next(rule for rule in catalogue if rule.id == rule_id)
        found = _found(rule)
        enabled = _ENABLED.where(rules.c.id == rule_id).exists()
        live = select(found.c.url_id, found.c.detail).where(enabled)
        return _affected_urls(connection, live.order_by(found.c.url_id))
