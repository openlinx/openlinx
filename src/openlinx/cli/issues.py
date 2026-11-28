"""List Issues or show the Affected URLs of one Rule in a selected Crawl."""

from pathlib import Path
from typing import Annotated

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import INVALID_VALUE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.paging import Page
from openlinx.output.writer import Format
from openlinx.services.query import (
    AFFECTED_URL_FIELDS,
    ISSUE_FIELDS,
    ISSUES,
    QueryRequest,
    issue_detail,
    issue_list,
)
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
CategoryOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--category",
        help="Only these Rule categories. Comma-separated or repeated.",
    ),
]


@command_meta(
    name=ISSUES,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=ISSUE_FIELDS,
    fields_by_argument={"rule_id": AFFECTED_URL_FIELDS},
    examples=[
        Example(
            f"{COMMAND_NAME} {ISSUES} --type issue,warning --priority high",
            "List high Priority Issues and Warnings.",
        ),
        Example(f"{COMMAND_NAME} {ISSUES} title-missing", "Show the Rule and its Affected URLs."),
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
    rule_id: Annotated[
        str | None, typer.Argument(metavar="RULE-ID", help="Show this Rule and its Affected URLs.")
    ] = None,
) -> Page:
    """List the Issues of a Crawl or show the Affected URLs of one Rule."""
    request = QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl)
    if rule_id is not None:
        for flag, values in (
            ("--type", issue_types),
            ("--priority", priorities),
            ("--category", categories),
        ):
            if values is not None:
                raise OpenLinxError(
                    INVALID_VALUE,
                    f"{flag} filters the Issue list and cannot be used with a Rule id.",
                    hint="Omit the Rule id to filter the Issue list.",
                    details={"flag": flag},
                )
        return issue_detail(request, rule_id, limit=limit, cursor=cursor, fields=fields)
    return issue_list(
        request,
        issue_types=issue_types or (),
        priorities=priorities or (),
        categories=categories or (),
        limit=limit,
        cursor=cursor,
        fields=fields,
    )
