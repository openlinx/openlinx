"""The app factory and the console script (design D8 of 010-add-workspace-and-cli-contract)."""

from typing import Annotated

import typer

from spider import APP_NAME, __version__
from spider.cli.commands import commands
from spider.cli.runner import SpiderGroup
from spider.output.writer import Output


def _print_version(ctx: typer.Context, value: bool) -> None:
    if value:
        output: Output = ctx.obj
        output.text(f"{APP_NAME} {__version__}\n")
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


def build_app() -> typer.Typer:
    app = typer.Typer(
        name=APP_NAME,
        cls=SpiderGroup,
        pretty_exceptions_enable=False,
        add_completion=False,
    )
    app.callback()(root)
    app.command()(commands)
    return app


def main() -> None:
    build_app()()
