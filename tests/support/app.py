"""The fixture app the scenarios use (design D8 of 010-add-workspace-and-cli-contract)."""

import typer

from spider.cli.app import AppExtra, build_app
from tests.support.settings import ExampleSettings


def example_app() -> typer.Typer:
    return build_app(extra=AppExtra(settings_tables={"example": ExampleSettings}))
