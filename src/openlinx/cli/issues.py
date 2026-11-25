"""Expose the Issue list and detail Commands for a selected Crawl."""

from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperCommand

from openlinx.cli.click_compat import Context
from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import USAGE_ERROR
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.paging import Page
from openlinx.output.writer import Format
from openlinx.services.query import (
    AFFECTED_URL_FIELDS,
    ISSUE,
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


class IssueListCommand(TyperCommand):
    """Point a caller who passed a Rule id to the detail Command."""

    allow_extra_args = True

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        extra = super().parse_args(ctx, args)
        if extra and not ctx.resilient_parsing:
            raise OpenLinxError(
                USAGE_ERROR,
                f"{COMMAND_NAME} {ISSUES} takes no positional arguments.",
                hint=f"Pass the Rule id to {COMMAND_NAME} {ISSUE} <rule-id>.",
            )
        return extra


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
    categories: CategoryOpt = None,
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
        categories=categories or (),
        limit=limit,
        cursor=cursor,
        fields=fields,
    )


@command_meta(
    name=ISSUE,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=AFFECTED_URL_FIELDS,
    examples=[
        Example(
            f"{COMMAND_NAME} {ISSUE} internal-4xx --fields url",
            "List the URLs affected by the internal-4xx Rule.",
        )
    ],
)
def issue(
    rule_id: Annotated[str, typer.Argument(metavar="RULE_ID", help="The recorded Rule id.")],
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """Show the Rule as recorded for the Crawl and page its Affected URLs."""
    return issue_detail(
        QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl),
        rule_id,
        limit=limit,
        cursor=cursor,
        fields=fields,
    )
