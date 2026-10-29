"""The app factory and the console script (design D8 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

import typer

from openlinx import __version__
from openlinx.cli.commands import commands
from openlinx.cli.crawl import crawl
from openlinx.cli.init import init
from openlinx.cli.meta import check_command
from openlinx.cli.runner import Invocation, OpenLinxGroup
from openlinx.cli.schema import schema
from openlinx.naming import COMMAND_NAME, PRODUCT_NAME
from openlinx.workspace.tables import SettingsTables


def _print_version(ctx: typer.Context, value: bool) -> None:
    if value:
        invocation: Invocation = ctx.obj
        invocation.output.text(f"{PRODUCT_NAME} {__version__}\n")
        raise typer.Exit


def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Print the version and exit."
        ),
    ] = False,
) -> None:
    """Agent-first SEO crawler."""


@dataclass(frozen=True)
class AppExtra:
    # Table name to its "module:Class" reference.
    settings_tables: Mapping[str, str] = field(default_factory=dict)
    commands: Sequence[Callable[..., Any]] = ()


def build_app(extra: AppExtra | None = None) -> typer.Typer:
    extra = extra or AppExtra()
    tables = SettingsTables()
    tables.register("crawl", "openlinx.crawl.settings:CrawlSettings")
    tables.register("store", "openlinx.store.settings:StoreSettings")
    for name, reference in extra.settings_tables.items():
        tables.register(name, reference)

    class AppGroup(OpenLinxGroup):
        settings_tables = tables

    app = typer.Typer(
        name=COMMAND_NAME,
        cls=AppGroup,
        pretty_exceptions_enable=False,
        add_completion=False,
        # Plain Click help: cheaper for agents to parse, and rich stays off the startup path.
        rich_markup_mode=None,
    )
    app.callback()(root)
    registered: list[Callable[..., Any]] = [commands, crawl, init, schema, *extra.commands]
    for command in registered:
        app.command(name=check_command(command).name)(command)
    return app


def main() -> None:
    build_app()()
