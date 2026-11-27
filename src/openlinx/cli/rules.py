"""Expose the Rule catalogue through the list and show Commands."""

from pathlib import Path
from typing import Annotated, Any

import typer

from openlinx.cli.meta import CommandGroup, Example, command_meta
from openlinx.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from openlinx.cli.runner import Invocation
from openlinx.naming import COMMAND_NAME
from openlinx.output.paging import Fields, Page, fingerprint, paginate, select_fields
from openlinx.output.writer import Format
from openlinx.services.rules import RulesRequest, rule_item, rule_items

LIST = "rules list"
SHOW = "rules show"
RULE_FIELDS = (
    "id",
    "category",
    "issue_type",
    "priority",
    "applies_to",
    "enabled",
    "thresholds",
    "description",
    "why_it_matters",
    "how_to_fix",
)
LIST_FIELDS = Fields(available=RULE_FIELDS, default=RULE_FIELDS)


@command_meta(
    name=LIST,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=LIST_FIELDS,
    examples=[
        Example(f"{COMMAND_NAME} {LIST} --fields id,priority", "List Rule ids and priorities.")
    ],
)
def list_rules(
    ctx: typer.Context,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
    workspace_dir: WorkspaceOpt = None,
) -> Page:
    """List the Rules that turn a Crawl's data into Issues, in catalogue order."""
    invocation: Invocation = ctx.obj
    request = RulesRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir)
    settings_file, items = rule_items(request, invocation.settings_tables)
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(LIST, {"workspace": settings_file.as_posix()}),
        fields=select_fields(fields, LIST_FIELDS),
    )


@command_meta(
    name=SHOW,
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[Example(f"{COMMAND_NAME} {SHOW} title-too-long", "Show a Rule and its thresholds.")],
)
def show_rule(
    ctx: typer.Context,
    rule_id: Annotated[str, typer.Argument(metavar="ID", help="The Rule id.")],
    output_format: FormatOpt = Format.JSON,
    workspace_dir: WorkspaceOpt = None,
) -> dict[str, Any]:
    """Show one Rule with the same fields as an item from rules list."""
    invocation: Invocation = ctx.obj
    request = RulesRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir)
    return rule_item(request, invocation.settings_tables, rule_id)


RULES_GROUP = CommandGroup(
    name="rules",
    summary="Describe the Rules that turn a Crawl's data into Issues.",
    commands=(list_rules, show_rule),
    default=list_rules,
)
