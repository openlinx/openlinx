"""Expose the Rule catalogue as a paged Command."""

from openlinx.cli.meta import CommandGroup, Example, command_meta
from openlinx.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.paging import Fields, Page, fingerprint, paginate, select_fields
from openlinx.output.writer import Format
from openlinx.services.rules import rule_items

LIST = "rules list"
RULE_FIELDS = (
    "id",
    "category",
    "issue_type",
    "priority",
    "applies_to",
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


RULES_GROUP = CommandGroup(
    name="rules",
    summary="Describe the Rules that turn a Crawl's data into Issues.",
    commands=(list_rules,),
    default=list_rules,
)
