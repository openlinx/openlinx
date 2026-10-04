"""Registering Commands on the app (design D7 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable
from typing import Any

import pytest

from spider.cli.app import AppExtra, build_app
from spider.cli.meta import command_meta
from spider.cli.options import FormatOpt
from spider.output.paging import Fields
from spider.output.writer import Format


def no_format() -> dict[str, Any]:
    return {}


def document_with_json_lines(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


def rows_without_fields(output_format: FormatOpt = Format.JSONL) -> list[Any]:
    return []


@pytest.mark.parametrize(
    "command",
    [
        no_format,
        command_meta(output="document", formats=[Format.JSON])(no_format),
        command_meta(output="document", formats=[Format.JSON, Format.JSONL])(
            document_with_json_lines
        ),
        command_meta(output="rows", formats=[Format.JSONL])(rows_without_fields),
        command_meta(
            output="rows", formats=[Format.JSONL, Format.TABLE], fields=Fields(("n",), ("n",))
        )(rows_without_fields),
    ],
)
def test_a_command_its_output_kind_cannot_serve_is_refused(command: Callable[..., Any]) -> None:
    with pytest.raises(TypeError):
        build_app(extra=AppExtra(commands=[command]))


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def table_first(output_format: FormatOpt = Format.TABLE) -> dict[str, Any]:
    return {}


@command_meta(output="list", formats=[Format.JSON], fields=Fields(("n", "sq"), ("n", "size")))
def unavailable_default_field(output_format: FormatOpt = Format.JSON, limit: int = 50) -> Any:
    return None


@pytest.mark.parametrize("command", [table_first, unavailable_default_field])
def test_default_format_comes_first_and_default_fields_are_available(
    command: Callable[..., Any],
) -> None:
    with pytest.raises(TypeError, match=command.__name__):
        build_app(extra=AppExtra(commands=[command]))
