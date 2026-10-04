"""The global flags, defined once (design D7 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Annotated

import typer

from spider.output.writer import Format

FormatOpt = Annotated[Format, typer.Option("--format", help="Output format.")]
WorkspaceOpt = Annotated[Path | None, typer.Option("--workspace", help="The Workspace folder.")]
LimitOpt = Annotated[int, typer.Option("--limit", help="The most items to print.")]
CursorOpt = Annotated[
    str | None, typer.Option("--cursor", help="The next_cursor of the previous page.")
]
