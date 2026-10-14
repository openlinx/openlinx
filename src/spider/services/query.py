"""The Query Service: reading a Crawl for the query Commands (050-add-query-and-segments D14)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.rules.registry import RULES
from spider.store.query import ordered_issues
from spider.store.reading import reading
from spider.store.selection import resolve_crawl
from spider.workspace.discovery import resolve_workspace


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryRequest:
    cwd: Path
    home: Path
    workspace: Path | None
    # The --crawl reference: latest, a crawl id or the path of a crawl file.
    crawl: str


def issue_list(request: QueryRequest) -> list[dict[str, Any]]:
    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    crawl_file = resolve_crawl(request.crawl, workspace=workspace, cwd=request.cwd)
    with reading(crawl_file.path) as connection:
        return ordered_issues(connection, RULES)
