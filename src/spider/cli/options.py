"""The global flags, defined once (design D7 of 010-add-workspace-and-cli-contract)."""

import inspect
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperOption

from spider.cli.click_compat import Command
from spider.naming import DATA_DIR_NAME, GLOBAL_DATA_DIR, SETTINGS_FILE_NAME
from spider.output.writer import Format
from spider.store.records import LATEST, SecretNames
from spider.workspace.tables import SettingsTables


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
        f"{DATA_DIR_NAME}/ or {SETTINGS_FILE_NAME}, else the global Workspace {GLOBAL_DATA_DIR}.",
    ),
    GLOBAL,
]
CrawlOpt = Annotated[
    str,
    typer.Option(
        "--crawl",
        help=f"The Crawl to read: {LATEST} (the Crawl that started last), a crawl id, "
        "or the path of a crawl file.",
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


def is_secret_option(extra: OptionMeta, tables: SettingsTables) -> bool:
    # An option mapped to a setting inherits it; check_command refuses an option with both.
    return extra.secret if extra.setting is None else tables.is_secret(extra.setting)


def secret_names(command: Command, tables: SettingsTables) -> SecretNames:
    flags = frozenset(
        name
        for param, extra in options_with_meta(command)
        if is_secret_option(extra, tables)
        for name in param.opts
    )
    # Every secret setting, not only this Command's: crawl.config records every table.
    return SecretNames(flags, tables.secret_settings())
