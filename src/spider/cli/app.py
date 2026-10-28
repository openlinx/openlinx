"""The app factory and the console script (design D8 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

import typer

from spider import __version__
from spider.cli.commands import commands
from spider.cli.crawl import crawl
from spider.cli.init import init
from spider.cli.meta import check_command
from spider.cli.runner import Invocation, SpiderGroup
from spider.cli.schema import schema
from spider.naming import APP_NAME
from spider.workspace.tables import SettingsTables


def _print_version(ctx: typer.Context, value: bool) -> None:
    if value:
        invocation: Invocation = ctx.obj
        invocation.output.text(f"{APP_NAME} {__version__}\n")
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
    tables.register("crawl", "spider.crawl.settings:CrawlSettings")
    tables.register("store", "spider.store.settings:StoreSettings")
    tables.register("content_area", "spider.extract.settings:ContentAreaSettings")
    for name, reference in extra.settings_tables.items():
        tables.register(name, reference)

    class AppGroup(SpiderGroup):
        settings_tables = tables

    app = typer.Typer(
        name=APP_NAME,
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
