"""Resolve a Crawl and return its Issue list."""

from dataclasses import dataclass
from pathlib import Path

from openlinx.output.paging import Page
from openlinx.store.records import LATEST
from openlinx.workspace.discovery import resolve_workspace


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryRequest:
    cwd: Path
    home: Path
    workspace: Path | None = None
    crawl: str = LATEST


def issue_list(request: QueryRequest) -> Page:
    """Return the small Rule catalogue's current Issues in contract order."""
    from openlinx.rules.registry import RULES
    from openlinx.store.query import ordered_issues_in
    from openlinx.store.reading import reading
    from openlinx.store.selection import resolve_crawl

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    crawl_file = resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
    with reading(crawl_file.path, identity=crawl_file.identity, snapshot=True) as connection:
        items = ordered_issues_in(connection, crawl_file.path, RULES)
    return Page(items=items, total=len(items), next_cursor=None)
