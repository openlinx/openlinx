"""`spider rules list` and `spider rules show` (040-add-rules D11, D18)."""

from typing import Annotated, Any

import typer

from spider.cli.meta import CommandGroup, Example, command_meta
from spider.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt
from spider.naming import APP_NAME
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.output.writer import Format
from spider.services.rules import RULE_FIELDS, rule_item, rule_items

LIST = "rules list"
SHOW = "rules show"
LIST_FIELDS = Fields(available=RULE_FIELDS, default=RULE_FIELDS)


@command_meta(
    name=LIST,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=LIST_FIELDS,
    examples=[
        Example(
            f"{APP_NAME} {LIST} --fields id,issue_type,priority",
            "List each Rule with its Issue Type and Priority.",
        )
    ],
)
def list_rules(
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """List the Rules that turn a Crawl's data into Issues, in catalogue order."""
    return paginate(
        rule_items(),
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(LIST, {}),
        fields=select_fields(fields, LIST_FIELDS),
    )


@command_meta(
    name=SHOW,
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[Example(f"{APP_NAME} {SHOW} title-too-long", "Show one Rule and its thresholds.")],
)
def show_rule(
    rule_id: Annotated[str, typer.Argument(help="The Rule id.")],
    output_format: FormatOpt = Format.JSON,
) -> dict[str, Any]:
    """Show one Rule, with the fields of a rules list item."""
    return rule_item(rule_id)


RULES_GROUP = CommandGroup(
    name="rules",
    summary="Describe the Rules that turn a Crawl's data into Issues.",
    commands=(list_rules, show_rule),
    default=list_rules,
)
