"""Show the stored detail of a Page."""

from pathlib import Path
from typing import Annotated, Any

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, FormatOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.writer import Format
from openlinx.services.query import QueryRequest
from openlinx.services.query import page as read_page
from openlinx.store.records import LATEST


@command_meta(
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[Example(f"{COMMAND_NAME} page https://example.com/", "Show a Page and its Issues.")],
)
def page(
    url: Annotated[str, typer.Argument(help="URL of the recorded Page.")],
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    headers: Annotated[
        bool, typer.Option("--headers", help="Show recorded response headers.")
    ] = False,
) -> dict[str, Any]:
    """Show the columns, Issues, redirects and Link counts of a Page."""
    request = QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl)
    return read_page(request, url, headers=headers)
