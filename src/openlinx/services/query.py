"""Resolve a Crawl and return its Issue list."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from openlinx.output.codes import INVALID_VALUE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.paging import Fields, Page, decode_cursor, fingerprint, paginate, select_fields
from openlinx.store.records import LATEST, IssueType, Priority
from openlinx.workspace.discovery import resolve_workspace

ISSUES = "issues"
_ISSUE_ITEM = ("rule_id", "category", "issue_type", "priority", "affected_count", "description")
ISSUE_FIELDS = Fields(available=_ISSUE_ITEM, default=_ISSUE_ITEM)


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
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Page:
    """Return one page of matching Issues from the selected Crawl's snapshot."""
    from openlinx.rules.registry import RULES
    from openlinx.store.query import ordered_issues_in
    from openlinx.store.reading import reading
    from openlinx.store.selection import resolve_crawl

    chosen = select_fields(fields, ISSUE_FIELDS)
    types = _filter_values(issue_types, "--type", get_args(IssueType.__value__))
    priority = _filter_values(priorities, "--priority", get_args(Priority.__value__))
    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    crawl_file = resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
    bound = fingerprint(ISSUES, {"crawl": crawl_file.id, "type": types, "priority": priority})
    # Check the cursor before a live read runs the enabled Rules.
    if cursor is not None:
        decode_cursor(cursor, bound)
    with reading(crawl_file.path, snapshot=True) as connection:
        items = ordered_issues_in(connection, RULES, issue_types=types, priorities=priority)
    return paginate(items, limit=limit, cursor=cursor, fingerprint=bound, fields=chosen)


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
