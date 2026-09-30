"""The root Typer app and the `spider` console script (design D7 of 000-scaffold-project)."""

import sys
from typing import Annotated

import typer

from spider import APP_NAME, __version__

app = typer.Typer(
    name=APP_NAME,
    pretty_exceptions_enable=False,
    add_completion=False,
    no_args_is_help=True,
)


def _print_version(value: bool) -> None:
    if value:
        # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
        sys.stdout.buffer.write(f"{APP_NAME} {__version__}\n".encode())
        raise typer.Exit


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Print the version and exit."
        ),
    ] = False,
) -> None:
    """Agent-first SEO crawler."""


def main() -> None:
    app()
