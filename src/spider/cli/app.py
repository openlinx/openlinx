"""The app factory and the console script (010-add-workspace-and-cli-contract D8; 040 D18)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from spider import __version__
from spider.cli.click_compat import Context
from spider.cli.commands import commands
from spider.cli.crawl import crawl
from spider.cli.init import init
from spider.cli.meta import CommandGroup, check_command
from spider.cli.rules import RULES_GROUP
from spider.cli.runner import Invocation, SpiderGroup, option_before_the_command
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
    commands: Sequence[Callable[..., Any] | CommandGroup] = ()


def build_app(extra: AppExtra | None = None) -> typer.Typer:
    extra = extra or AppExtra()
    tables = SettingsTables()
    tables.register("crawl", "spider.crawl.settings:CrawlSettings")
    tables.register("store", "spider.store.settings:StoreSettings")
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
    registered = [commands, crawl, init, RULES_GROUP, schema, *extra.commands]
    for entry in registered:
        if isinstance(entry, CommandGroup):
            app.add_typer(_group_app(entry), name=entry.name)
        else:
            app.command(name=check_command(entry).name)(entry)
    return app


def _group_app(group: CommandGroup) -> typer.Typer:
    names = {}
    for command in group.commands:
        parent, _, name = check_command(command).name.rpartition(" ")
        if parent != group.name:
            raise TypeError(f"Command {command.__name__} is not named under {group.name}.")
        names[command] = name
    if group.default not in names:
        raise TypeError(f"The default of group {group.name} is not one of its Commands.")
    default = names[group.default]

    class Group(TyperGroup):
        def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
            if not args:
                return super().parse_args(ctx, [default])
            # Options are taken after the Command name only, as global flags are.
            if args[0].startswith("-") and args[0] not in ctx.help_option_names:
                flag = args[0].partition("=")[0]
                raise option_before_the_command(flag, f"{group.name} {default}")
            return super().parse_args(ctx, args)

    app = typer.Typer(cls=Group, help=group.summary, rich_markup_mode=None)
    for command, name in names.items():
        app.command(name=name)(command)
    return app


def main() -> None:
    build_app()()
