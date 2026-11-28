"""Adapt the stop Command to the Crawl Control Service."""

from pathlib import Path
from typing import Annotated

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, FormatOpt, WorkspaceOpt
from openlinx.clock import SystemClock
from openlinx.naming import COMMAND_NAME
from openlinx.output.writer import Format
from openlinx.services.control import (
    DEFAULT_STOP_WAIT_SECONDS,
    StopRequest,
    StopResult,
    request_stop,
)
from openlinx.store.records import LATEST


@command_meta(
    output="document",
    formats=[Format.JSON],
    examples=[Example(f"{COMMAND_NAME} stop", "Request a graceful stop of the latest Crawl.")],
)
def stop(
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    wait: Annotated[
        int,
        typer.Option(
            "--wait",
            min=0,
            help="Seconds to wait for the Crawl to stop. "
            "Use 0 to return after the request commits.",
        ),
    ] = DEFAULT_STOP_WAIT_SECONDS,
    output_format: FormatOpt = Format.JSON,
) -> StopResult:
    """Request a graceful stop of a Crawl through its crawl file."""
    request = StopRequest(
        cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl, wait_seconds=wait
    )
    return request_stop(request, SystemClock())
