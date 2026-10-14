"""Rules run over a crawl file, and the pass that stores their Issues (040-add-rules D5, D15)."""

from collections.abc import Callable, Mapping, Sequence
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

from spider.rules.model import Rule, find_rule, rule_not_found
from spider.store.reading import reading
from spider.store.records import AffectedUrl, CrawlState, Issue, UrlIssue
from spider.store.schema import affected_urls, crawl, issues, rules
from spider.store.writer import CrawlWriter

_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id, rules.c.category, rules.c.issue_type, rules.c.priority).where(
    rules.c.enabled == 1
)
_STATE = select(crawl.c.state)
_RECORDED_RULE = select(rules.c.id).where(rules.c.id == bindparam("rule_id"))
_STORED_URL_ISSUES = select(affected_urls.c.rule_id, affected_urls.c.detail).where(
    affected_urls.c.url_id == bindparam("url_id")
)
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
    with reading(crawl_file) as connection:
        if _materialised(connection):
            return _stored_affected_urls(connection, rule_id)
        return _live_affected_urls(connection, find_rule(catalogue, rule_id))


def live_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    rule = find_rule(catalogue, rule_id)
    with reading(crawl_file) as connection:
        return _live_affected_urls(connection, rule)


def stored_affected_urls(crawl_file: Path, rule_id: str) -> list[AffectedUrl]:
    with reading(crawl_file) as connection:
        return _stored_affected_urls(connection, rule_id)


def read_url_issues(crawl_file: Path, url_id: int, catalogue: Sequence[Rule]) -> list[UrlIssue]:
    """The Rules that fired for one URL, in catalogue order, as stored for a completed or
    stopped Crawl, otherwise computed live (D16)."""
    with reading(crawl_file) as connection:
        if _materialised(connection):
            return _stored_url_issues(connection, url_id, catalogue)
        return _live_url_issues(connection, url_id, catalogue)


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
    return _in_catalogue_order(stored, catalogue)


def _live_affected_urls(connection: Connection, rule: Rule) -> list[AffectedUrl]:
    if rule.id not in _enabled_rule_ids(connection):
        return []
    return sorted(_affected_urls(connection, rule), key=lambda url: url.url_id)


def _stored_affected_urls(connection: Connection, rule_id: str) -> list[AffectedUrl]:
    # Known by the file's own rules table: a file of a later tool holds Rules the catalogue lacks.
    if connection.execute(_RECORDED_RULE, {"rule_id": rule_id}).first() is None:
        raise rule_not_found(rule_id)
    return [
        AffectedUrl(url_id=row.url_id, detail=_detail(row.detail))
        for row in connection.execute(_STORED_AFFECTED_URLS, {"rule_id": rule_id})
    ]


def _live_url_issues(
    connection: Connection, url_id: int, catalogue: Sequence[Rule]
) -> list[UrlIssue]:
    enabled = _enabled_rule_ids(connection)
    found = []
    for rule in catalogue:
        if rule.id not in enabled:
            continue
        query = _found(rule)
        found += [
            UrlIssue(rule_id=rule.id, url_id=url_id, detail=_detail(row.detail))
            for row in connection.execute(select(query).where(query.c.url_id == url_id))
        ]
    return found


def _stored_url_issues(
    connection: Connection, url_id: int, catalogue: Sequence[Rule]
) -> list[UrlIssue]:
    # By the index affected_urls_url_id (D14).
    stored = {
        row.rule_id: UrlIssue(rule_id=row.rule_id, url_id=url_id, detail=_detail(row.detail))
        for row in connection.execute(_STORED_URL_ISSUES, {"url_id": url_id})
    }
    return _in_catalogue_order(stored, catalogue)


def _in_catalogue_order[T](by_rule_id: Mapping[str, T], catalogue: Sequence[Rule]) -> list[T]:
    # A file from a later tool may hold rows of Rules this catalogue lacks: they come last.
    ids = [rule.id for rule in catalogue if rule.id in by_rule_id]
    return [by_rule_id[rule_id] for rule_id in ids + sorted(by_rule_id.keys() - set(ids))]


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
