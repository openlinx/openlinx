"""Rules run over a crawl file, and the pass that stores their Issues (040-add-rules D5, D15)."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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
)

from spider.rules.model import Rule, find_rule
from spider.store.reading import reading
from spider.store.records import AffectedUrl, CrawlState, Issue
from spider.store.schema import affected_urls, crawl, issues, rules
from spider.store.writer import CrawlWriter

_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id, rules.c.category, rules.c.issue_type, rules.c.priority).where(
    rules.c.enabled == 1
)
_STATE = select(crawl.c.state)
_STORED_ISSUES = select(issues)
_STORED_AFFECTED_URLS = (
    select(affected_urls.c.url_id, affected_urls.c.detail)
    .where(affected_urls.c.rule_id == bindparam("rule_id"))
    .order_by(affected_urls.c.url_id)
)


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    with reading(crawl_file) as connection:
        return _affected_urls(connection, rule)


def affected_urls_unit(rule: Rule) -> Callable[[Connection], None]:
    """A unit that replaces the Rule's rows in affected_urls with those its query returns."""
    found = _found(rule)
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def unit(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return unit


async def materialise_issues(writer: CrawlWriter, catalogue: Sequence[Rule]) -> None:
    """The post-crawl pass: the Rules that the Crawl's rules table marks enabled (D5, D6)."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule in catalogue:
        if rule.id in enabled:
            await writer.run_async(affected_urls_unit(rule))


def read_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    """The Issues as stored for a completed or stopped Crawl, otherwise computed live (D16)."""
    with reading(crawl_file) as connection:
        if _materialised(connection):
            return _stored_issues(connection, catalogue)
        return _live_issues(connection, catalogue)


def live_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    """The Issues that the queries of the Crawl's enabled Rules give now, in catalogue order."""
    with reading(crawl_file) as connection:
        return _live_issues(connection, catalogue)


def stored_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    """The Issues of the issues view, in catalogue order, then those of other Rules by id."""
    with reading(crawl_file) as connection:
        return _stored_issues(connection, catalogue)


def read_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    """One Rule's Affected URLs by URL id, as stored for a completed or stopped Crawl,
    otherwise computed live (D16)."""
    rule = find_rule(catalogue, rule_id)
    with reading(crawl_file) as connection:
        if _materialised(connection):
            return _stored_affected_urls(connection, rule)
        return _live_affected_urls(connection, rule)


def live_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    rule = find_rule(catalogue, rule_id)
    with reading(crawl_file) as connection:
        return _live_affected_urls(connection, rule)


def stored_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    rule = find_rule(catalogue, rule_id)
    with reading(crawl_file) as connection:
        return _stored_affected_urls(connection, rule)


def _live_issues(connection: Connection, catalogue: Sequence[Rule]) -> list[Issue]:
    recorded = {row.id: row for row in connection.execute(_ENABLED)}
    found = []
    for rule in catalogue:
        row = recorded.get(rule.id)
        if row is None:
            continue
        count = connection.execute(select(func.count()).select_from(_found(rule))).scalar_one()
        if count:
            found.append(
                Issue(
                    rule_id=rule.id,
                    category=row.category,
                    issue_type=row.issue_type,
                    priority=row.priority,
                    affected_count=count,
                )
            )
    return found


def _stored_issues(connection: Connection, catalogue: Sequence[Rule]) -> list[Issue]:
    stored = {row.rule_id: Issue(**row._asdict()) for row in connection.execute(_STORED_ISSUES)}
    # A file from a later tool may hold Issues of Rules this catalogue lacks: they come last.
    ids = [rule.id for rule in catalogue if rule.id in stored]
    return [stored[rule_id] for rule_id in ids + sorted(stored.keys() - set(ids))]


def _live_affected_urls(connection: Connection, rule: Rule) -> list[AffectedUrl]:
    if rule.id not in _enabled_rule_ids(connection):
        return []
    return sorted(_affected_urls(connection, rule), key=lambda url: url.url_id)


def _stored_affected_urls(connection: Connection, rule: Rule) -> list[AffectedUrl]:
    return [
        AffectedUrl(url_id=row.url_id, detail=_detail(row.detail))
        for row in connection.execute(_STORED_AFFECTED_URLS, {"rule_id": rule.id})
    ]


def _found(rule: Rule) -> Subquery:
    return text(rule.reproduce_sql).columns(url_id=Integer, detail=Text).subquery()


def _affected_urls(connection: Connection, rule: Rule) -> list[AffectedUrl]:
    return [
        AffectedUrl(url_id=url_id, detail=_detail(detail))
        for url_id, detail in connection.execute(select(_found(rule)))
    ]


def _enabled_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(row.id for row in connection.execute(_ENABLED))


def _detail(stored: str | None) -> Any:
    return None if stored is None else orjson.loads(stored)


def _materialised(connection: Connection) -> bool:
    # 020 writes completed and stopped only after the post-crawl passes; a resume sets running
    # first, and failed and interrupted get no pass, so they are read live (D16).
    state: CrawlState = connection.execute(_STATE).scalar_one()
    return state in ("completed", "stopped")
