"""Evaluate catalogue Rules and materialise their Affected URLs in the Crawl."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import orjson
from sqlalchemy import (
    Connection,
    Integer,
    Select,
    Subquery,
    Text,
    bindparam,
    delete,
    false,
    func,
    insert,
    literal,
    select,
    text,
    true,
    union_all,
)

from openlinx.store.preview import PREVIEW_NO_ROWS, PREVIEW_PLACEHOLDER_IDS
from openlinx.store.reading import reading
from openlinx.store.records import AffectedUrl, CrawlState, Issue, UrlIssue
from openlinx.store.rule_queries import RuleQuery, rule_not_computable, rule_not_found
from openlinx.store.schema import affected_urls, crawl, issues, rules
from openlinx.store.writer import Unit


def evaluate_rule(crawl_file: Path, rule: RuleQuery) -> list[AffectedUrl]:
    """Evaluate the registered query for an enabled, active Rule in the Crawl snapshot."""
    with reading(crawl_file) as connection:
        if not _recorded_rule_is_evaluable(connection, rule.id):
            return []
        return _affected_urls(connection, select(_found(rule)))


def _found(rule: RuleQuery) -> Subquery:
    # text() recognises :name inside SQL literals. Escape it and terminate trailing SQL comments.
    sql = rule.reproduce_sql.replace(":", "\\:") + "\n"
    return text(sql).columns(url_id=Integer, detail=Text).subquery()


def _affected_urls(connection: Connection, statement: Select[int, str | None]) -> list[AffectedUrl]:
    return [
        AffectedUrl(url_id=url_id, detail=decode_detail(detail))
        for url_id, detail in connection.execute(statement)
    ]


_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
# The preview query recorded an empty result. Keep it empty when reading or continuing
# that Crawl after the same Rule id acquires a real query. Never run stored SQL here.
_EVALUABLE = (rules.c.enabled == 1) & ~(
    rules.c.id.in_(PREVIEW_PLACEHOLDER_IDS) & (rules.c.reproduce_sql == PREVIEW_NO_ROWS)
)
_EVALUABLE_IDS = select(rules.c.id).where(_EVALUABLE)


def affected_urls_unit(rule: RuleQuery) -> Unit[None]:
    """Replace one Rule's result atomically, including when its new result is empty."""
    found = _found(rule)
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def replace_rows(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return replace_rows


def _evaluable_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(connection.scalars(_EVALUABLE_IDS))


class _IssueWriter(Protocol):
    async def run_async[T](self, unit: Unit[T]) -> T: ...


async def materialise_issues(writer: _IssueWriter, units: Mapping[str, Unit[None]]) -> None:
    """Run the installed Rule units enabled and active in this Crawl's snapshot."""
    evaluable = await writer.run_async(_evaluable_rule_ids)
    for rule_id, unit in units.items():
        if rule_id in evaluable:
            await writer.run_async(unit)


_ISSUE_STATE = select(crawl.c.state)
_STORED_ISSUES = select(issues)
_ISSUE_COLUMNS = (
    rules.c.id.label("rule_id"),
    rules.c.category,
    rules.c.issue_type,
    rules.c.priority,
)
_EMPTY_ISSUES = select(*_ISSUE_COLUMNS, literal(0).label("affected_count")).where(false())
_AFFECTED = select(affected_urls.c.url_id, affected_urls.c.detail)
_RULE_EVALUABLE = select(_EVALUABLE).where(rules.c.id == bindparam("rule_id"))
_RECORDED_IDS = select(rules.c.id)


def _materialised(connection: Connection) -> bool:
    state: CrawlState = connection.execute(_ISSUE_STATE).scalar_one()
    return state in ("completed", "stopped")


def _evaluable_rules(connection: Connection, catalogue: Sequence[RuleQuery]) -> list[RuleQuery]:
    # SQLite resolves even unreachable query branches. A Rule absent or disabled in the
    # Crawl can name columns introduced after that Crawl was created.
    evaluable = _evaluable_rule_ids(connection)
    return [rule for rule in catalogue if rule.id in evaluable]


def issues_in(
    connection: Connection,
    catalogue: Sequence[RuleQuery],
    *,
    rule_ids: frozenset[str] | None = None,
) -> Select[Any]:
    """A composable issues view on a reading() connection."""
    if _materialised(connection):
        if rule_ids is None:
            return _STORED_ISSUES
        # Filter the count by the primary key prefix. A filter on the grouped view's
        # projected Rule id scans all Affected URLs before discarding other Rules.
        return (
            select(*_ISSUE_COLUMNS, func.count().label("affected_count"))
            .join_from(affected_urls, rules, affected_urls.c.rule_id == rules.c.id)
            .where(affected_urls.c.rule_id.in_(rule_ids))
            .group_by(affected_urls.c.rule_id)
        )
    counts = [
        select(*_ISSUE_COLUMNS, func.count().label("affected_count"))
        .select_from(rules.join(_found(rule), true()))
        .where(rules.c.id == rule.id)
        .group_by(rules.c.id)
        for rule in _evaluable_rules(connection, catalogue)
        if rule_ids is None or rule.id in rule_ids
    ]
    if not counts:
        return _EMPTY_ISSUES
    return select(union_all(*counts).subquery())


def live_issue_affected_in(connection: Connection, catalogue: Sequence[RuleQuery]) -> Subquery:
    """The live Affected URLs for enabled Issue-type Rules, for the Health Score."""
    issue_ids: frozenset[str] = frozenset(
        connection.scalars(select(rules.c.id).where(rules.c.issue_type == "issue"))
    )
    branches = []
    for rule in _evaluable_rules(connection, catalogue):
        if rule.id in issue_ids:
            found = _found(rule)
            branches.append(select(literal(rule.id).label("rule_id"), found.c.url_id))
    if not branches:
        return select(affected_urls.c.rule_id, affected_urls.c.url_id).where(false()).subquery()
    return union_all(*branches).subquery()


def _recorded_rule_is_evaluable(connection: Connection, rule_id: str) -> bool:
    evaluable: bool | None = connection.execute(
        _RULE_EVALUABLE, {"rule_id": rule_id}
    ).scalar_one_or_none()
    if evaluable is None:
        raise rule_not_found(rule_id, connection.scalars(_RECORDED_IDS).all())
    return evaluable


def affected_urls_in(
    connection: Connection, rule_id: str, catalogue: Sequence[RuleQuery]
) -> Select[Any]:
    """One Rule's url_id and raw JSON detail on a reading() connection."""
    evaluable = _recorded_rule_is_evaluable(connection, rule_id)
    if _materialised(connection):
        return _AFFECTED.where(affected_urls.c.rule_id == rule_id)
    if not evaluable:
        return _AFFECTED.where(false())
    for rule in catalogue:
        if rule.id == rule_id:
            return select(_found(rule))
    raise rule_not_computable(rule_id)


def _catalogue_order[T](by_id: Mapping[str, T], catalogue: Sequence[RuleQuery]) -> list[T]:
    known = [rule.id for rule in catalogue if rule.id in by_id]
    return [by_id[rule_id] for rule_id in (*known, *sorted(by_id.keys() - set(known)))]


def read_issues(crawl_file: Path, catalogue: Sequence[RuleQuery]) -> list[Issue]:
    """Issues in catalogue order, followed by other recorded Rules in Rule id order."""
    with reading(crawl_file) as connection:
        by_id = {
            row.rule_id: Issue(
                rule_id=row.rule_id,
                category=row.category,
                issue_type=row.issue_type,
                priority=row.priority,
                affected_count=row.affected_count,
            )
            for row in connection.execute(issues_in(connection, catalogue))
        }
    return _catalogue_order(by_id, catalogue)


def read_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[RuleQuery]
) -> list[AffectedUrl]:
    """One Rule's Affected URLs from the final pass or current rows, ordered by URL id."""
    with reading(crawl_file) as connection:
        found = affected_urls_in(connection, rule_id, catalogue).subquery()
        return _affected_urls(
            connection, select(found.c.url_id, found.c.detail).order_by(found.c.url_id)
        )


def decode_detail(detail: str | None) -> dict[str, Any] | None:
    return None if detail is None else orjson.loads(detail)


def read_url_issues(
    crawl_file: Path, url_id: int, catalogue: Sequence[RuleQuery]
) -> list[UrlIssue]:
    """Issues for one URL in catalogue order, followed by other stored Rules in Rule id order."""
    with reading(crawl_file) as connection:
        return url_issues_in(connection, url_id, catalogue)


def url_issues_in(
    connection: Connection, url_id: int, catalogue: Sequence[RuleQuery]
) -> list[UrlIssue]:
    """Read the URL's Issue details within the caller's snapshot."""
    if _materialised(connection):
        statement = select(affected_urls.c.rule_id, affected_urls.c.detail).where(
            affected_urls.c.url_id == url_id
        )
    else:
        branches = []
        for rule in _evaluable_rules(connection, catalogue):
            found = _found(rule)
            branches.append(
                select(literal(rule.id).label("rule_id"), found.c.detail).where(
                    found.c.url_id == url_id
                )
            )
        if not branches:
            return []
        # Evaluate the branches in one statement for readers without a snapshot.
        statement = select(union_all(*branches).subquery())
    by_id = {
        rule_id: UrlIssue(rule_id=rule_id, url_id=url_id, detail=decode_detail(detail))
        for rule_id, detail in connection.execute(statement)
    }
    return _catalogue_order(by_id, catalogue)
