"""Resolve a Crawl and query its snapshot."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from openlinx.output.codes import INVALID_VALUE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.paging import (
    Fields,
    Page,
    decode_cursor,
    encode_cursor,
    fingerprint,
    invalid_cursor,
    paginate,
    project,
    select_fields,
)
from openlinx.store.page_records import PAGE_COLUMNS
from openlinx.store.records import LATEST, CrawlFile, IssueType, Priority, RuleCategory
from openlinx.workspace.discovery import resolve_workspace

if TYPE_CHECKING:
    from openlinx.store.sql import SqlResult

ISSUES = "issues"
PAGES = "pages"
PAGE_FIELDS = Fields(
    available=PAGE_COLUMNS,
    default=(
        "address",
        "status_code",
        "indexability",
        "indexability_status",
        "title_1",
        "crawl_depth",
    ),
)
_ISSUE_ITEM = ("rule_id", "category", "issue_type", "priority", "affected_count", "description")
ISSUE_FIELDS = Fields(available=_ISSUE_ITEM, default=_ISSUE_ITEM)
_AFFECTED_URL_ITEM = ("url", "detail")
AFFECTED_URL_FIELDS = Fields(available=_AFFECTED_URL_ITEM, default=_AFFECTED_URL_ITEM)


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryRequest:
    cwd: Path
    home: Path
    workspace: Path | None = None
    crawl: str = LATEST


def issue_list(
    request: QueryRequest,
    *,
    issue_types: Sequence[str] = (),
    priorities: Sequence[str] = (),
    categories: Sequence[str] = (),
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    """Return one page of matching Issues from the selected Crawl's snapshot."""
    from openlinx.rules.registry import RULES
    from openlinx.store.query import ordered_issues_in
    from openlinx.store.reading import reading_selected

    chosen = select_fields(fields, ISSUE_FIELDS)
    types = _filter_values(issue_types, "--type", get_args(IssueType.__value__))
    priority = _filter_values(priorities, "--priority", get_args(Priority.__value__))
    category = _filter_values(categories, "--category", get_args(RuleCategory.__value__))
    crawl_file = _crawl_file(request)
    selection = {"crawl": crawl_file.id, "type": types, "priority": priority}
    # Keep existing cursors valid for the same query without a category filter.
    if category:
        selection["category"] = category
    bound = fingerprint(ISSUES, selection)
    # Check the cursor before a live read runs the enabled Rules.
    if cursor is not None:
        decode_cursor(cursor, bound)
    with reading_selected(crawl_file) as connection:
        items = ordered_issues_in(
            connection,
            crawl_file.path,
            RULES,
            issue_types=types,
            priorities=priority,
            categories=category,
        )
    return paginate(items, limit=limit, cursor=cursor, fingerprint=bound, fields=chosen)


def issue_detail(
    request: QueryRequest,
    rule_id: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    """Read a recorded Rule and page its Affected URLs by URL within one snapshot."""
    from openlinx.rules.registry import RULES
    from openlinx.store.query import issue_detail_in
    from openlinx.store.reading import reading_selected

    chosen = select_fields(fields, AFFECTED_URL_FIELDS)
    crawl_file = _crawl_file(request)
    bound = fingerprint("issue_detail", {"crawl": crawl_file.id, "rule_id": rule_id})
    after: str | None = None
    if cursor is not None:
        keyset = decode_cursor(cursor, bound)
        if not isinstance(keyset, list) or len(keyset) != 1 or not isinstance(keyset[0], str):
            raise invalid_cursor()
        after = keyset[0]

    window = limit + 1 if limit > 0 else 0
    with reading_selected(crawl_file) as connection:
        rule, total, found = issue_detail_in(
            connection, crawl_file.path, rule_id, RULES, after=after, limit=window
        )
    items = found[:limit]
    next_cursor = (
        encode_cursor(bound, [items[-1]["url"]]) if limit > 0 and len(found) > limit else None
    )
    return Page(project(items, chosen), total, next_cursor, header={"rule": rule})


def pages(
    request: QueryRequest,
    *,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
    where: str | None = None,
) -> Page:
    """Return one window and the total of matching Pages from the selected Crawl."""
    from openlinx.query.where import parse
    from openlinx.store.query_pages import pages_in
    from openlinx.store.reading import reading_selected

    chosen = select_fields(fields, PAGE_FIELDS)
    expression = parse(where) if where is not None else None
    crawl_file = _crawl_file(request)
    selection = {"crawl": crawl_file.id}
    if where is not None:
        selection["where"] = where
    bound = fingerprint(PAGES, selection)
    after: str | None = None
    if cursor is not None:
        keyset = decode_cursor(cursor, bound)
        if not isinstance(keyset, list) or len(keyset) != 1 or not isinstance(keyset[0], str):
            raise invalid_cursor()
        after = keyset[0]

    window = limit + 1 if limit > 0 else 0
    with reading_selected(crawl_file) as connection:
        total, found = pages_in(
            connection, after=after, limit=window, fields=chosen, where=expression
        )
    items = found[:limit]
    next_cursor = (
        encode_cursor(bound, [items[-1]["address"]]) if limit > 0 and len(found) > limit else None
    )
    return Page(project(items, chosen), total, next_cursor)


def sql_query(request: QueryRequest, statement: str, *, limit: int, timeout: float) -> "SqlResult":
    """Read SQL from the selected Crawl using the Store's restricted reader."""
    from openlinx.store.sql import read_sql

    return read_sql(_crawl_file(request), statement, limit=limit, timeout=timeout)


def _crawl_file(request: QueryRequest) -> CrawlFile:
    from openlinx.store.selection import resolve_crawl

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    return resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)


def _filter_values(values: Sequence[str], flag: str, accepted: tuple[str, ...]) -> tuple[str, ...]:
    normalized = [value.strip().lower() for group in values for value in group.split(",")]
    for value in normalized:
        if value not in accepted:
            raise OpenLinxError(
                INVALID_VALUE,
                f"{flag} value {value!r} is not one of the accepted values.",
                hint=f"Use {flag} with any of: {', '.join(accepted)}.",
                details={"flag": flag, "value": value, "accepted": list(accepted)},
            )
    return tuple(sorted(set(normalized)))
