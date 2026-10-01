"""The global flags, defined once (design D7 of 010-add-workspace-and-cli-contract)."""

from typing import Annotated

import typer

from spider.output.writer import Format

FormatOpt = Annotated[Format, typer.Option("--format", help="Output format.")]
