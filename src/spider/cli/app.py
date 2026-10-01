"""The app factory and the console script (design D8 of 010-add-workspace-and-cli-contract)."""

from typing import Annotated

import typer

from spider import APP_NAME, __version__
from spider.cli.commands import commands
from spider.output.writer import Output


def _print_version(value: bool) -> None:
    if value:
        Output().text(f"{APP_NAME} {__version__}\n")
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
        pretty_exceptions_enable=False,
        add_completion=False,
        no_args_is_help=True,
    )
    app.callback()(root)
    app.command()(commands)
    return app


def main() -> None:
    build_app()()
