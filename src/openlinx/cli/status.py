"""Adapt the status Command to the Crawl Status Service."""

from pathlib import Path
from typing import cast

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, FormatOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.writer import Format
from openlinx.store.records import LATEST


@command_meta(
    output="document",
    formats=[Format.JSON],
    examples=[Example(f"{COMMAND_NAME} status", "Show the status of the latest Crawl.")],
)
def status(
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
) -> dict[str, object]:
    """Show the recorded state of a Crawl."""
    from msgspec import to_builtins

    from openlinx.services.status import show_status

    result = show_status(Path.cwd(), Path.home(), workspace_dir=workspace_dir, crawl=crawl)
    return cast(dict[str, object], to_builtins(result))
