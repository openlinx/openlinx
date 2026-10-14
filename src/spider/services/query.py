"""The Query Service: reading a Crawl for the query Commands (050-add-query-and-segments D14)."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, get_args

from spider.output.codes import INVALID_VALUE
from spider.output.diagnostics import SpiderError
from spider.output.paging import (
    Fields,
    Page,
    decode_cursor,
    fingerprint,
    keyset_after,
    keyset_page,
    paginate,
    select_fields,
)
from spider.rules.registry import RULES
from spider.store.records import CrawlFile, IssueFilters, IssueType, Priority, RuleCategory
from spider.workspace.discovery import resolve_workspace

ISSUES = "issues"
ISSUE_ITEM = ("rule_id", "category", "issue_type", "priority", "affected_count", "description")
ISSUE_FIELDS = Fields(available=ISSUE_ITEM, default=ISSUE_ITEM)
NO_FILTERS = IssueFilters()


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryRequest:
    cwd: Path
    home: Path
    workspace: Path | None
    # The --crawl reference: latest, a crawl id or the path of a crawl file.
    crawl: str


def issue_filters(
    *,
    issue_types: Iterable[str] = (),
    priorities: Iterable[str] = (),
    categories: Iterable[str] = (),
) -> IssueFilters:
    """The filters of repeatable flags, each of whose values may list several by commas."""
    return IssueFilters(
        issue_types=_filter_values("--type", issue_types, get_args(IssueType.__value__)),
        priorities=_filter_values("--priority", priorities, get_args(Priority.__value__)),
        categories=_filter_values("--category", categories, get_args(RuleCategory.__value__)),
    )


def _filter_values(flag: str, values: Iterable[str], accepted: tuple[str, ...]) -> frozenset[str]:
    found = []
    for listed in values:
        given = [value.strip().lower() for value in listed.split(",")]
        if "" in given:
            raise SpiderError(
                INVALID_VALUE,
                f"{flag} {listed!r} has an empty value.",
                hint=f"Separate the values with single commas, such as {flag} "
                f"{accepted[0]},{accepted[1]}.",
                details={"flag": flag, "value": listed, "accepted": list(accepted)},
            )
        found += given
    unknown = [value for value in found if value not in accepted]
    if unknown:
        raise SpiderError(
            INVALID_VALUE,
            f"{flag} {unknown[0]} is not one of the accepted values.",
            hint=f"Use {flag} with any of: {', '.join(accepted)}.",
            details={"flag": flag, "value": unknown[0], "accepted": list(accepted)},
        )
    return frozenset(found)


def issue_list(
    request: QueryRequest,
    filters: IssueFilters = NO_FILTERS,
    *,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    # Imported here, as every store module: sqlalchemy stays off the CLI's startup path.
    from spider.store.query import ordered_issues
    from spider.store.reading import reading

    # Checked before the Issues are read: on a running Crawl that runs every Rule's query.
    chosen = select_fields(fields, ISSUE_FIELDS)
    crawl_file = _crawl_file(request)
    bound = _fingerprint(
        crawl_file,
        type=sorted(filters.issue_types),
        priority=sorted(filters.priorities),
        category=sorted(filters.categories),
    )
    if cursor is not None:
        decode_cursor(cursor, bound)
    with reading(crawl_file.path) as connection:
        items = ordered_issues(connection, RULES, filters)
    return paginate(items, limit=limit, cursor=cursor, fingerprint=bound, fields=chosen)


def issue_detail(
    request: QueryRequest, rule_id: str, *, limit: int = 50, cursor: str | None = None
) -> Page:
    """One Issue: its Rule as the Crawl recorded it, and a page of the Rule's Affected URLs,
    by keyset in URL order (design D4, D14)."""
    from spider.store.query import affected_url_page, recorded_rule
    from spider.store.reading import reading

    crawl_file = _crawl_file(request)
    bound = _fingerprint(crawl_file, rule_id=rule_id)
    after = keyset_after(cursor, bound, (str,))
    with reading(crawl_file.path) as connection:
        # First: the reader refuses a rule id the Crawl's rules table lacks.
        total, found = affected_url_page(
            connection, rule_id, RULES, after=None if after is None else after[0], limit=limit + 1
        )
        rule = recorded_rule(connection, rule_id)
    page = keyset_page(found, total, limit=limit, fingerprint=bound, keys=("url",))
    return replace(page, header={"rule": rule})


def _crawl_file(request: QueryRequest) -> CrawlFile:
    from spider.store.selection import resolve_crawl

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    return resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)


def _fingerprint(crawl_file: CrawlFile, **selection: Any) -> str:
    # The resolved id, never latest: a cursor reused after a new Crawl started is refused.
    return fingerprint(ISSUES, {"crawl": crawl_file.id, **selection})
