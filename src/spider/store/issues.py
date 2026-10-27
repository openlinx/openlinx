"""Rules run over a crawl file, and the pass that stores their Issues and the Health Score
(040-add-rules D5, D8, D15)."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
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
    distinct,
    false,
    func,
    insert,
    literal,
    select,
    text,
    union_all,
    update,
)

from spider.clock import Clock
from spider.rules.health import health_score
from spider.rules.model import Rule, rule_not_computable, rule_not_found
from spider.store.reading import reading
from spider.store.records import AffectedUrl, CrawlState, Health, Issue, UrlIssue
from spider.store.schema import affected_urls, crawl, issues, pages, rules
from spider.store.writer import CrawlWriter

_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id, rules.c.issue_type).where(rules.c.enabled == 1)
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
_STORED_DETAILS = select(affected_urls.c.url_id, affected_urls.c.detail)
_NO_AFFECTED_URLS = _STORED_DETAILS.where(false())
_NO_ISSUES = select(*_ISSUE_COLUMNS, literal(0).label("affected_count")).where(false())
# The selectables of health(): every Internal Page, and the Affected URLs as stored.
INTERNAL_PAGES = select(pages.c.url_id)
STORED_AFFECTED_URLS = select(affected_urls.c.rule_id, affected_urls.c.url_id)
_NO_RULE_URLS = STORED_AFFECTED_URLS.where(false())
_ISSUE_RULES = select(rules.c.id).where(rules.c.issue_type == "issue", rules.c.enabled == 1)


class IssueReader(Protocol):
    """A Crawl's Issues, read one way: as stored by its last pass, or computed live (D16)."""

    def issues(self) -> Select[Any]:
        """The Issues, in the shape of the issues view."""
        ...

    def affected_urls(self, rule_id: str) -> Select[Any]:
        """One Rule's Affected URLs, in the shape of affected_urls; rule_not_found when the
        Crawl's rules table lacks the Rule."""
        ...

    def url_issues(self, url_id: int) -> list[UrlIssue]:
        """The Rules that fired for one URL, in catalogue order."""
        ...

    def health_affected(self) -> Select[Any]:
        """The Affected URLs, rule_id and url_id, that health() counts."""
        ...


def issue_reader(connection: Connection, catalogue: Sequence[Rule]) -> IssueReader:
    """The one choice between a Crawl's stored and live Issues (D16)."""
    if _materialised(connection):
        return StoredIssues(connection, catalogue)
    return LiveIssues(connection, catalogue)


class StoredIssues:
    """The Issues that the Crawl's last pass stored, valid for a completed or stopped Crawl."""

    def __init__(self, connection: Connection, catalogue: Sequence[Rule]) -> None:
        self._connection = connection
        self._catalogue = catalogue

    def issues(self) -> Select[Any]:
        return _STORED_ISSUES

    def affected_urls(self, rule_id: str) -> Select[Any]:
        # Known by the file's own rules table: a file of a later tool holds Rules the catalogue
        # lacks.
        _recorded_rule(self._connection, rule_id)
        return _STORED_DETAILS.where(affected_urls.c.rule_id == rule_id)

    def url_issues(self, url_id: int) -> list[UrlIssue]:
        # By the index affected_urls_url_id (D14).
        stored = {
            row.rule_id: UrlIssue(rule_id=row.rule_id, url_id=url_id, detail=_detail(row.detail))
            for row in self._connection.execute(_STORED_URL_ISSUES, {"url_id": url_id})
        }
        return _in_catalogue_order(stored, self._catalogue)

    def health_affected(self) -> Select[Any]:
        return STORED_AFFECTED_URLS


class LiveIssues:
    """The Issues that each enabled Rule's query gives on the rows as they are now."""

    def __init__(self, connection: Connection, catalogue: Sequence[Rule]) -> None:
        self._connection = connection
        self._catalogue = catalogue
        issue_types = {row.id: row.issue_type for row in connection.execute(_ENABLED)}
        # A Rule that the file records but this catalogue lacks is never computed (D15).
        self._enabled = [rule for rule in catalogue if rule.id in issue_types]
        self._issue_rules = [rule for rule in self._enabled if issue_types[rule.id] == "issue"]

    def issues(self) -> Select[Any]:
        counted = _union(
            [
                select(
                    *_ISSUE_COLUMNS,
                    select(func.count())
                    .select_from(_found(rule))
                    .scalar_subquery()
                    .label("affected_count"),
                ).where(rules.c.id == rule.id)
                for rule in self._enabled
            ],
            _NO_ISSUES,
        ).subquery()
        return select(counted).where(counted.c.affected_count > 0)

    def affected_urls(self, rule_id: str) -> Select[Any]:
        if not _recorded_rule(self._connection, rule_id):
            return _NO_AFFECTED_URLS
        rule = next((rule for rule in self._catalogue if rule.id == rule_id), None)
        if rule is None:
            raise rule_not_computable(rule_id)
        return select(_found(rule))

    def url_issues(self, url_id: int) -> list[UrlIssue]:
        found = []
        for rule in self._enabled:
            query = _found(rule)
            found += [
                UrlIssue(rule_id=rule.id, url_id=url_id, detail=_detail(row.detail))
                for row in self._connection.execute(select(query).where(query.c.url_id == url_id))
            ]
        return found

    def health_affected(self) -> Select[Any]:
        # Only the Rules that can lower the score: the rest would be counted and then dropped.
        return _union(
            [
                select(literal(rule.id).label("rule_id"), _found(rule).c.url_id)
                for rule in self._issue_rules
            ],
            _NO_RULE_URLS,
        )


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


def health(connection: Connection, rated: Select[Any], affected: Select[Any]) -> Health:
    """The Health Score of the Pages among the url_id that `rated` selects, counted against the
    Affected URLs, rule_id and url_id, that `affected` selects (D8)."""
    # Only Pages count: a Segment of URLs also holds URLs that are no Page.
    rated_pages = select(pages.c.url_id).where(
        pages.c.url_id.in_(select(rated.subquery().c.url_id))
    )
    found = affected.subquery()
    counted = select(
        select(func.count()).select_from(rated_pages.subquery()).scalar_subquery(),
        select(func.count(distinct(found.c.url_id)))
        .where(found.c.url_id.in_(rated_pages), found.c.rule_id.in_(_ISSUE_RULES))
        .scalar_subquery(),
    )
    internal, affected_pages = connection.execute(counted).one()
    return Health(
        score=health_score(internal, affected_pages),
        internal_pages=internal,
        affected_pages=affected_pages,
    )


def health_affected_in(connection: Connection, catalogue: Sequence[Rule]) -> Select[Any]:
    """The Affected URLs, rule_id and url_id, for health(), as the Issues reader reads them."""
    return issue_reader(connection, catalogue).health_affected()


async def materialise_issues(writer: CrawlWriter, catalogue: Sequence[Rule], clock: Clock) -> None:
    """The post-crawl pass: the Rules that the Crawl's rules table marks enabled, then the
    Health Score over their rows (D5, D6, D8)."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule in catalogue:
        if rule.id in enabled:
            await writer.run_async(affected_urls_unit(rule))
    await writer.run_async(_health_unit(clock.now()))


def _health_unit(calculated_at: datetime) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)
        connection.execute(
            update(crawl).values(
                health_score=found.score,
                health_internal_page_count=found.internal_pages,
                health_affected_page_count=found.affected_pages,
                health_calculated_at=calculated_at,
            )
        )

    return unit


def issues_in(connection: Connection, catalogue: Sequence[Rule]) -> Select[Any]:
    """The Issues, in the shape of the issues view, as the Issues reader reads them."""
    return issue_reader(connection, catalogue).issues()


def affected_urls_in(
    connection: Connection, rule_id: str, catalogue: Sequence[Rule]
) -> Select[Any]:
    """One Rule's Affected URLs, in the shape of affected_urls, as the Issues reader reads
    them."""
    return issue_reader(connection, catalogue).affected_urls(rule_id)


def read_issues(crawl_file: Path, catalogue: Sequence[Rule]) -> list[Issue]:
    """The Issues of issues_in, in catalogue order, then those of other Rules by id."""
    with reading(crawl_file) as connection:
        found = {
            row.rule_id: Issue(**row._asdict())
            for row in connection.execute(issues_in(connection, catalogue))
        }
        return _in_catalogue_order(found, catalogue)


def read_affected_urls(
    crawl_file: Path, rule_id: str, catalogue: Sequence[Rule]
) -> list[AffectedUrl]:
    """The Affected URLs of affected_urls_in, by URL id."""
    with reading(crawl_file) as connection:
        found = affected_urls_in(connection, rule_id, catalogue).subquery()
        return [
            AffectedUrl(url_id=row.url_id, detail=_detail(row.detail))
            for row in connection.execute(select(found).order_by(found.c.url_id))
        ]


def read_url_issues(crawl_file: Path, url_id: int, catalogue: Sequence[Rule]) -> list[UrlIssue]:
    """The Rules that fired for one URL, in catalogue order, as the Issues reader reads them."""
    with reading(crawl_file) as connection:
        return issue_reader(connection, catalogue).url_issues(url_id)


def _union(selects: Sequence[Select[Any]], empty: Select[Any]) -> Select[Any]:
    if not selects:
        return empty
    return select(union_all(*selects).subquery())


def _recorded_rule(connection: Connection, rule_id: str) -> bool:
    """Whether the Crawl's rules table marks the Rule enabled; rule_not_found if it lacks it."""
    enabled: bool | None = connection.execute(
        _RECORDED_RULE, {"rule_id": rule_id}
    ).scalar_one_or_none()
    if enabled is None:
        raise rule_not_found(rule_id, connection.execute(_RECORDED_IDS).scalars().all())
    return enabled


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


def _enabled_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(row.id for row in connection.execute(_ENABLED))


def _detail(stored: str | None) -> Any:
    return None if stored is None else orjson.loads(stored)


def _materialised(connection: Connection) -> bool:
    # 020 writes completed and stopped only after the post-crawl passes; a resume sets running
    # first, and failed and interrupted get no pass, so they are read live (D16).
    state: CrawlState = connection.execute(_STATE).scalar_one()
    return state in ("completed", "stopped")
