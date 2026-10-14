"""The Query Service: reading a Crawl for the query Commands (050-add-query-and-segments D14)."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields

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


def filter_values(values: Iterable[str]) -> frozenset[str]:
    """The values of a repeatable filter flag, each of which may list several by commas."""
    return frozenset(value.strip().lower() for listed in values for value in listed.split(","))


def issue_list(
    request: QueryRequest,
    filters: IssueFilters = NO_FILTERS,
    *,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    # Imported here: sqlalchemy stays off the CLI's startup path.
    from spider.rules.registry import RULES
    from spider.store.query import ordered_issues
    from spider.store.reading import reading
    from spider.store.selection import resolve_crawl
    from spider.workspace.discovery import resolve_workspace

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    crawl_file = resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
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
