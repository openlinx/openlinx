"""Show the committed rows of a Crawl as a versioned summary."""

from pathlib import Path
from typing import Annotated, Any

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, FormatOpt, OptionMeta, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.table import TitledTables
from openlinx.output.writer import Format
from openlinx.services.query import (
    DEFAULT_SUMMARY_TOP,
    MAX_SUMMARY_TOP,
    SUMMARY_TOP_HINT,
    QueryRequest,
)
from openlinx.services.query import summary as read_summary
from openlinx.store.records import LATEST


@command_meta(
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[Example(f"{COMMAND_NAME} summary --top 5", "Summarise the latest Crawl.")],
)
def summary(
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    top: Annotated[
        int,
        typer.Option("--top", min=0, max=MAX_SUMMARY_TOP, help="Number of top Issues."),
        OptionMeta(invalid_hint=SUMMARY_TOP_HINT),
    ] = DEFAULT_SUMMARY_TOP,
) -> dict[str, Any] | TitledTables:
    """Summarise the Pages, responses, Health Score and Issues of a Crawl."""
    from msgspec import to_builtins

    from openlinx.output.summary import summary_tables

    request = QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl)
    document: dict[str, Any] = to_builtins(read_summary(request, top=top))
    return summary_tables(document) if output_format is Format.TABLE else document
