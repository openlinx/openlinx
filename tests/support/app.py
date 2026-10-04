"""The fixture app the scenarios use (design D8 of 010-add-workspace-and-cli-contract)."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import typer

from spider.cli.app import AppExtra, build_app
from spider.cli.meta import command_meta
from spider.cli.options import CursorOpt, FieldsOpt, FormatOpt, LimitOpt
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.output.writer import Format
from tests.support.settings import ExampleSettings

EXAMPLE_FIELDS = Fields(available=("n", "sq"), default=("n",))


@command_meta(
    output="list", formats=[Format.JSON, Format.JSONL, Format.TABLE], fields=EXAMPLE_FIELDS
)
def example_list(
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
    odd: Annotated[bool, typer.Option("--odd", help="Only the items with an odd n.")] = False,
) -> Page:
    """The example list Command of the cli-contract scenarios."""
    items = [{"n": n, "sq": n * n} for n in range(1, 6) if n % 2 or not odd]
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint("example-list", {"odd": odd}),
        fields=select_fields(fields, EXAMPLE_FIELDS),
    )


N_ONLY = Fields(available=("n",), default=("n",))


@command_meta(output="list", formats=[Format.JSON, Format.JSONL, Format.TABLE], fields=N_ONLY)
def example_long_list(
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """A list Command whose items are n=1 to n=60."""
    items = [{"n": n} for n in range(1, 61)]
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint("example-long-list", {}),
        fields=select_fields(fields, N_ONLY),
    )


@command_meta(output="rows", formats=[Format.JSONL], fields=N_ONLY)
def example_rows(output_format: FormatOpt = Format.JSONL) -> Iterator[Any]:
    """A rows Command that returns the rows n=1 and n=2."""
    yield {"n": 1}
    yield {"n": 2}


@command_meta(output="rows", formats=[Format.JSONL], fields=N_ONLY)
def example_rows_waiting(signal: Path, output_format: FormatOpt = Format.JSONL) -> Iterator[Any]:
    """Yields n=1, waits up to 5 s for the signal file, then n=2, or n=-1 if it never came."""
    yield {"n": 1}
    deadline = time.monotonic() + 5
    while not signal.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    yield {"n": 2 if signal.exists() else -1}


def example_app() -> typer.Typer:
    return build_app(
        extra=AppExtra(
            settings_tables={"example": ExampleSettings},
            commands=[example_list, example_long_list, example_rows, example_rows_waiting],
        )
    )
