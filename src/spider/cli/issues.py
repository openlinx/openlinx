"""`spider issues` (050-add-query-and-segments D14)."""

from pathlib import Path
from typing import Annotated

import typer

from spider.cli.meta import Example, command_meta
from spider.cli.options import CrawlOpt, CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from spider.naming import APP_NAME
from spider.output.paging import Page
from spider.output.writer import Format
from spider.services.query import (
    ISSUE_FIELDS,
    ISSUES,
    IssueFilters,
    QueryRequest,
    filter_values,
    issue_list,
)
from spider.store.records import LATEST

TypeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--type",
        help="Only Issues of these Issue Types: issue, warning or opportunity. "
        "Comma-separated, or the flag repeated.",
    ),
]
PriorityOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--priority",
        help="Only Issues of these Priorities: high, medium or low. "
        "Comma-separated, or the flag repeated.",
    ),
]
CategoryOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--category",
        help="Only Issues of these Rule categories, such as titles. "
        "Comma-separated, or the flag repeated.",
    ),
]


@command_meta(
    name=ISSUES,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=ISSUE_FIELDS,
    examples=[
        Example(
            f"{APP_NAME} {ISSUES} --type issue --priority high",
            "List the Issues of Issue Type issue with high Priority.",
        )
    ],
)
def issues(
    issue_types: TypeOpt = None,
    priorities: PriorityOpt = None,
    categories: CategoryOpt = None,
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """List the Issues of a Crawl, the most serious first, with their Affected URL counts."""
    return issue_list(
        QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl),
        IssueFilters(
            issue_types=filter_values(issue_types or ()),
            priorities=filter_values(priorities or ()),
            categories=filter_values(categories or ()),
        ),
        limit=limit,
        cursor=cursor,
        fields=fields,
    )
