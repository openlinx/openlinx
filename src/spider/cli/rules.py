"""`spider rules` (040-add-rules, rules)."""

from spider.cli.meta import CommandGroup, command_meta
from spider.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.output.writer import Format
from spider.services.rules import rule_items

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


RULES = CommandGroup(
    "rules", "Describe the Rules that turn a Crawl's data into Issues.", (list_rules,), "list"
)
