"""`spider schema` (015-add-crawl-store D6; 018-add-schema-conventions D4)."""

from dataclasses import replace
from typing import Annotated

import typer

from spider.cli.meta import command_meta
from spider.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.output.writer import Format
from spider.services.schema import describe_schema

SCHEMA = "schema"
TABLE_FIELDS = ("name", "kind", "description", "columns", "indexes")
SCHEMA_FIELDS = Fields(available=TABLE_FIELDS, default=TABLE_FIELDS)


@command_meta(
    name=SCHEMA,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=SCHEMA_FIELDS,
)
def schema(
    table: Annotated[str | None, typer.Argument(help="Only this table.")] = None,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """List the public tables of a crawl file, with their columns."""
    description = describe_schema(table)
    page = paginate(
        description.tables,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(SCHEMA, {"table": table}),
        fields=select_fields(fields, SCHEMA_FIELDS),
    )
    return replace(page, header={"schema_version": description.schema_version})
