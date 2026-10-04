"""The app factory and the console script (design D8 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any

import typer

from spider import APP_NAME, __version__
from spider.cli.commands import commands
from spider.cli.init import init
from spider.cli.meta import check_command
from spider.cli.runner import Invocation, SpiderGroup
from spider.workspace.tables import SettingsTables

if TYPE_CHECKING:
    from pydantic import BaseModel


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
    settings_tables: "Mapping[str, type[BaseModel]]" = field(default_factory=dict)
    commands: Sequence[Callable[..., Any]] = ()


def build_app(extra: AppExtra | None = None) -> typer.Typer:
    extra = extra or AppExtra()
    tables = SettingsTables()
    for name, model in extra.settings_tables.items():
        tables.register(name, model)

    class AppGroup(SpiderGroup):
        settings_tables = tables

    app = typer.Typer(
        name=APP_NAME,
        cls=AppGroup,
        pretty_exceptions_enable=False,
        add_completion=False,
    )
    app.callback()(root)
    registered: list[Callable[..., Any]] = [commands, init, *extra.commands]
    for command in registered:
        app.command(name=check_command(command).name)(command)
    return app


def main() -> None:
    build_app()()
