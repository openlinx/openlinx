"""The Query Service: reading a Crawl for the query Commands (050-add-query-and-segments D14)."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from spider.output.codes import INVALID_VALUE
from spider.output.diagnostics import SpiderError
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.store.records import CrawlFile, IssueType, Priority, RuleCategory

# Each function imports the store inside its body: sqlalchemy stays off the CLI's startup path.

ISSUES = "issues"
ISSUE_ITEM = ("rule_id", "category", "issue_type", "priority", "affected_count", "description")
ISSUE_FIELDS = Fields(available=ISSUE_ITEM, default=ISSUE_ITEM)


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryRequest:
    cwd: Path
    home: Path
    workspace: Path | None
    # The --crawl reference: latest, a crawl id or the path of a crawl file.
    crawl: str


@dataclass(frozen=True, slots=True, kw_only=True)
class IssueFilters:
    """The accepted values of each filter; an empty set accepts every value."""

    issue_types: frozenset[str] = frozenset()
    priorities: frozenset[str] = frozenset()
    categories: frozenset[str] = frozenset()


NO_FILTERS = IssueFilters()


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
    found = frozenset(value.strip().lower() for listed in values for value in listed.split(","))
    unknown = sorted(found - set(accepted))
    if unknown:
        raise SpiderError(
            INVALID_VALUE,
            f"{flag} {unknown[0]} is not one of the accepted values.",
            hint=f"Use {flag} with any of: {', '.join(accepted)}.",
            details={"flag": flag, "value": unknown[0], "accepted": list(accepted)},
        )
    return found


def issue_list(
    request: QueryRequest,
    filters: IssueFilters = NO_FILTERS,
    *,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    from spider.rules.registry import RULES
    from spider.store.query import ordered_issues
    from spider.store.reading import reading

    crawl_file = _crawl_file(request)
    with reading(crawl_file.path) as connection:
        items = ordered_issues(
            connection,
            RULES,
            issue_types=filters.issue_types,
            priorities=filters.priorities,
            categories=filters.categories,
        )
    # The resolved id, never latest: a cursor reused after a new Crawl started is refused.
    selection = {
        "crawl": crawl_file.id,
        "type": sorted(filters.issue_types),
        "priority": sorted(filters.priorities),
        "category": sorted(filters.categories),
    }
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(ISSUES, selection),
        fields=select_fields(fields, ISSUE_FIELDS),
    )


def issue_detail(request: QueryRequest, rule_id: str) -> Page:
    """One Issue: its Rule as the Crawl recorded it, and the Rule's Affected URLs."""
    from spider.rules.registry import RULES
    from spider.store.query import affected_url_items, recorded_rule
    from spider.store.reading import reading

    with reading(_crawl_file(request).path) as connection:
        # First: the reader refuses a rule id the Crawl's rules table lacks.
        items = affected_url_items(connection, rule_id, RULES)
        rule = recorded_rule(connection, rule_id)
    return Page(items, len(items), None, header={"rule": rule})


def _crawl_file(request: QueryRequest) -> CrawlFile:
    from spider.store.selection import resolve_crawl
    from spider.workspace.discovery import resolve_workspace

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    return resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
