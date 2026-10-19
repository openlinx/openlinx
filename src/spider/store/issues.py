"""Rules run over a crawl file, and the pass that stores their Issues (040-add-rules D5, D15)."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import orjson
from sqlalchemy import (
    Connection,
    Integer,
    Select,
    Subquery,
    Text,
    bindparam,
    delete,
    distinct,
    false,
    func,
    insert,
    literal,
    select,
    text,
    union_all,
)

from spider.rules.health import health_score
from spider.rules.model import Rule, rule_not_computable, rule_not_found
from spider.store.reading import reading
from spider.store.records import AffectedUrl, CrawlState, Health, Issue, UrlIssue
from spider.store.schema import affected_urls, crawl, issues, pages, rules
from spider.store.writer import CrawlWriter

_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id).where(rules.c.enabled == 1)
_STATE = select(crawl.c.state)
_RECORDED_RULE = select(rules.c.enabled).where(rules.c.id == bindparam("rule_id"))
_RECORDED_IDS = select(rules.c.id)
_ISSUE_COLUMNS = (
    rules.c.id.label("rule_id"),
    rules.c.category,
    rules.c.issue_type,
    rules.c.priority,
)
_STORED_URL_ISSUES = select(affected_urls.c.rule_id, affected_urls.c.detail).where(
    affected_urls.c.url_id == bindparam("url_id")
)
_STORED_ISSUES = select(issues)
_STORED_AFFECTED_URLS = select(affected_urls.c.url_id, affected_urls.c.detail)
_NO_AFFECTED_URLS = _STORED_AFFECTED_URLS.where(false())
# The selectables of health(): every Internal Page, and the Affected URLs as stored.
INTERNAL_PAGES = select(pages.c.url_id)
STORED_AFFECTED_URLS = select(affected_urls.c.rule_id, affected_urls.c.url_id)
_ISSUE_RULES = select(rules.c.id).where(rules.c.issue_type == "issue")


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


def health(connection: Connection, pages: Select[Any], affected: Select[Any]) -> Health:
    """The Health Score of the Pages whose url_id `pages` selects, counted against the Affected
    URLs, rule_id and url_id, that `affected` selects (D8)."""
    page_ids = pages.subquery()
    found = affected.subquery()
    counted = select(
        select(func.count()).select_from(page_ids).scalar_subquery(),
        select(func.count(distinct(found.c.url_id)))
        .where(found.c.url_id.in_(select(page_ids.c.url_id)), found.c.rule_id.in_(_ISSUE_RULES))
        .scalar_subquery(),
    )
    internal, affected_pages = connection.execute(counted).one()
    return Health(
        score=health_score(internal, affected_pages),
        internal_pages=internal,
        affected_pages=affected_pages,
    )


def all_live_affected_urls(catalogue: Sequence[Rule]) -> Select[Any]:
    """The rule_id and url_id of the catalogue's Affected URLs, computed live, for health()
    while the Crawl runs."""
    found = [select(literal(rule.id).label("rule_id"), _found(rule).c.url_id) for rule in catalogue]
    return select(union_all(*found).subquery())


async def materialise_issues(writer: CrawlWriter, catalogue: Sequence[Rule]) -> None:
    """The post-crawl pass: the Rules that the Crawl's rules table marks enabled (D5, D6)."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule in catalogue:
        if rule.id in enabled:
            await writer.run_async(affected_urls_unit(rule))


def issues_in(connection: Connection, catalogue: Sequence[Rule]) -> Select[Any]:
    """The Issues, in the shape of the issues view, as stored for a completed or stopped
    Crawl, otherwise computed live (D16)."""
    if _materialised(connection):
        return _STORED_ISSUES
    return _live_issues(catalogue)


def affected_urls_in(
    connection: Connection, rule_id: str, catalogue: Sequence[Rule]
) -> Select[Any]:
    """One Rule's Affected URLs, in the shape of affected_urls, as stored for a completed or
    stopped Crawl, otherwise computed live (D16)."""
    if _materialised(connection):
        return _stored_affected_urls(connection, rule_id)
    return _live_affected_urls(connection, rule_id, catalogue)


def read_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    """The Issues of issues_in, in catalogue order, then those of other Rules by id."""
    with reading(crawl_file) as connection:
        return _issues(connection, issues_in(connection, catalogue), catalogue)


def live_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    with reading(crawl_file) as connection:
        return _issues(connection, _live_issues(catalogue), catalogue)


def stored_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    with reading(crawl_file) as connection:
        return _issues(connection, _STORED_ISSUES, catalogue)


def read_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    """The Affected URLs of affected_urls_in, by URL id."""
    with reading(crawl_file) as connection:
        return _affected(connection, affected_urls_in(connection, rule_id, catalogue))


def live_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    with reading(crawl_file) as connection:
        return _affected(connection, _live_affected_urls(connection, rule_id, catalogue))


def stored_affected_urls(crawl_file: Path, rule_id: str) -> list[AffectedUrl]:
    with reading(crawl_file) as connection:
        return _affected(connection, _stored_affected_urls(connection, rule_id))


def read_url_issues(crawl_file: Path, url_id: int, catalogue: Sequence[Rule]) -> list[UrlIssue]:
    """The Rules that fired for one URL, in catalogue order, as stored for a completed or
    stopped Crawl, otherwise computed live (D16)."""
    with reading(crawl_file) as connection:
        if _materialised(connection):
            return _stored_url_issues(connection, url_id, catalogue)
        return _live_url_issues(connection, url_id, catalogue)


def _live_issues(catalogue: Sequence[Rule]) -> Select[Any]:
    counted = union_all(
        *(
            select(
                *_ISSUE_COLUMNS,
                select(func.count())
                .select_from(_found(rule))
                .scalar_subquery()
                .label("affected_count"),
            ).where(rules.c.id == rule.id, rules.c.enabled == 1)
            for rule in catalogue
        )
    ).subquery()
    return select(counted).where(counted.c.affected_count > 0)


def _issues(connection: Connection, query: Select[Any], catalogue: Sequence[Rule]) -> list[Issue]:
    found = {row.rule_id: Issue(**row._asdict()) for row in connection.execute(query)}
    return _in_catalogue_order(found, catalogue)


def _live_affected_urls(
    connection: Connection, rule_id: str, catalogue: Sequence[Rule]
) -> Select[Any]:
    enabled = _recorded_rule(connection, rule_id)
    if not enabled:
        return _NO_AFFECTED_URLS
    rule = next((rule for rule in catalogue if rule.id == rule_id), None)
    if rule is None:
        raise rule_not_computable(rule_id)
    return select(_found(rule))


def _stored_affected_urls(connection: Connection, rule_id: str) -> Select[Any]:
    # Known by the file's own rules table: a file of a later tool holds Rules the catalogue lacks.
    _recorded_rule(connection, rule_id)
    return _STORED_AFFECTED_URLS.where(affected_urls.c.rule_id == rule_id)


def _recorded_rule(connection: Connection, rule_id: str) -> bool:
    """Whether the Crawl's rules table marks the Rule enabled; rule_not_found if it lacks it."""
    enabled: bool | None = connection.execute(
        _RECORDED_RULE, {"rule_id": rule_id}
    ).scalar_one_or_none()
    if enabled is None:
        raise rule_not_found(rule_id, connection.execute(_RECORDED_IDS).scalars().all())
    return enabled


def _affected(connection: Connection, query: Select[Any]) -> list[AffectedUrl]:
    found = query.subquery()
    return [
        AffectedUrl(url_id=row.url_id, detail=_detail(row.detail))
        for row in connection.execute(select(found).order_by(found.c.url_id))
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
    # text() reads :name as a parameter, even in a comment or a string: escaped, the SQL
    # that runs is reproduce_sql. The line break ends a trailing -- comment before the
    # subquery's closing parenthesis.
    written = rule.reproduce_sql.replace(":", "\\:") + "\n"
    return text(written).columns(url_id=Integer, detail=Text).subquery()


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
