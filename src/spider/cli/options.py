"""The global flags, defined once (design D7 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Annotated

import typer

from spider.output.writer import Format

FormatOpt = Annotated[Format, typer.Option("--format", help="Output format.")]
WorkspaceOpt = Annotated[Path | None, typer.Option("--workspace", help="The Workspace folder.")]
LimitOpt = Annotated[
    int, typer.Option("--limit", min=0, max=1000, help="The most items to print, from 0 to 1000.")
]
CursorOpt = Annotated[
    str | None, typer.Option("--cursor", help="The next_cursor of the previous page.")
]
FieldsOpt = Annotated[
    str | None, typer.Option("--fields", help="Comma-separated fields of each item.")
]

# Flags that mean the same on every Command that takes them, always after its name.
GLOBAL_FLAGS = frozenset({"--workspace", "--format", "--crawl"})
