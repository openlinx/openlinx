"""The global flags, defined once (design D7 of 010-add-workspace-and-cli-contract)."""

import inspect
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperOption

from spider import APP_NAME
from spider.cli.click_compat import Command
from spider.output.writer import Format


@dataclass(frozen=True)
class OptionMeta:
    """What `spider commands` says about an option beyond what Click knows."""

    is_global: bool = False
    setting: str | None = None
    secret: bool = False


GLOBAL = OptionMeta(is_global=True)
# The parameter every Command declares for --format; the wrapper and the runner read it.
FORMAT_PARAMETER = "output_format"

FormatOpt = Annotated[Format, typer.Option("--format", help="Output format."), GLOBAL]
WorkspaceOpt = Annotated[
    Path | None,
    typer.Option(
        "--workspace",
        # Symbolic, not the real home path, so the self-description is the same on every OS.
        help="The Workspace folder. Without it, the nearest folder upwards that holds "
        f".{APP_NAME}/ or {APP_NAME}.toml, else the global Workspace ~/.{APP_NAME}.",
    ),
    GLOBAL,
]
LimitOpt = Annotated[
    int, typer.Option("--limit", min=0, max=1000, help="The most items to print, from 0 to 1000.")
]
CursorOpt = Annotated[
    str | None, typer.Option("--cursor", help="The next_cursor of the previous page.")
]
FieldsOpt = Annotated[
    str | None, typer.Option("--fields", help="Comma-separated fields of each item.")
]


def option_meta(callback: Callable[..., Any], name: str) -> OptionMeta:
    # Click keeps no trace of extra Annotated metadata; the Command's own hints still have it.
    hints = typing.get_type_hints(inspect.unwrap(callback), include_extras=True)
    metadata = getattr(hints.get(name), "__metadata__", ())
    return next((item for item in metadata if isinstance(item, OptionMeta)), OptionMeta())


def options_with_meta(command: Command) -> Iterator[tuple[TyperOption, OptionMeta]]:
    for param in command.params:
        if isinstance(param, TyperOption) and command.callback is not None:
            yield param, option_meta(command.callback, str(param.name))
