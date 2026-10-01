"""The fixture app the scenarios use (design D8 of 010-add-workspace-and-cli-contract)."""

from typing import Any

import typer

from spider.cli.app import AppExtra, build_app
from spider.cli.meta import Fields, command_meta
from spider.cli.options import FormatOpt, LimitOpt
from spider.output.writer import Format
from tests.support.settings import ExampleSettings


@command_meta(
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=Fields(available=("n", "sq"), default=("n",)),
)
def example_list(output_format: FormatOpt = Format.JSON, limit: LimitOpt = 50) -> list[Any]:
    """The example list Command of the cli-contract scenarios."""
    return [{"n": n, "sq": n * n} for n in range(1, 6)]


def example_app() -> typer.Typer:
    return build_app(
        extra=AppExtra(settings_tables={"example": ExampleSettings}, commands=[example_list])
    )
