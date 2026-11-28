"""List Pages from the selected Crawl."""

from pathlib import Path
from typing import Annotated

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, CursorOpt, FieldsOpt, FormatOpt, LimitOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.paging import Page
from openlinx.output.writer import Format
from openlinx.services import query
from openlinx.store.records import LATEST


@command_meta(
    name=query.PAGES,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=query.PAGE_FIELDS,
    examples=[
        Example(f"{COMMAND_NAME} {query.PAGES} --fields address,title_1", "List Page titles."),
    ],
)
def pages(
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
    where: Annotated[str | None, typer.Option(help="Only Pages matching this filter.")] = None,
) -> Page:
    """List the Pages of a Crawl."""
    request = query.QueryRequest(
        cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl
    )
    return query.pages(request, limit=limit, cursor=cursor, fields=fields, where=where)
