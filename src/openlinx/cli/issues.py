"""List Issues from a selected Crawl through the Query Service."""

from pathlib import Path
from typing import Annotated

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.paging import Page
from openlinx.output.writer import Format
from openlinx.services.query import ISSUE_FIELDS, ISSUES, QueryRequest, issue_list
from openlinx.store.records import LATEST

TypeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--type",
        help="Only these Issue Types: issue, warning or opportunity. Comma-separated or repeated.",
    ),
]
PriorityOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--priority",
        help="Only these Priorities: high, medium or low. Comma-separated or repeated.",
    ),
]


@command_meta(
    name=ISSUES,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=ISSUE_FIELDS,
    examples=[
        Example(
            f"{COMMAND_NAME} {ISSUES} --type issue,warning --priority high",
            "List high Priority Issues and Warnings.",
        )
    ],
)
def issues(
    issue_types: TypeOpt = None,
    priorities: PriorityOpt = None,
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """List the Issues of a Crawl with their Affected URL counts."""
    return issue_list(
        QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl),
        issue_types=issue_types or (),
        priorities=priorities or (),
        limit=limit,
        cursor=cursor,
        fields=fields,
    )
