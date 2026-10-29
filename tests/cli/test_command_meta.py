"""Registering Commands on the app (design D7 of 010-add-workspace-and-cli-contract)."""

import re
from collections.abc import Callable
from typing import Annotated, Any

import pytest
import typer

from openlinx.cli.app import AppExtra, build_app
from openlinx.cli.meta import command_meta
from openlinx.cli.options import FormatOpt, OptionMeta
from openlinx.output.paging import Fields
from openlinx.output.writer import Format


def no_format() -> dict[str, Any]:
    return {}


def document_with_json_lines(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


def rows_without_fields(output_format: FormatOpt = Format.JSONL) -> list[Any]:
    return []


def list_without_cursor(output_format: FormatOpt = Format.JSON, limit: int = 50) -> Any:
    return None


@pytest.mark.parametrize(
    ("command", "problem"),
    [
        (no_format, "no_format has no @command_meta"),
        (
            command_meta(output="document", formats=[Format.JSON])(no_format),
            "no_format: it does not declare output_format",
        ),
        (
            command_meta(output="document", formats=[Format.JSON, Format.JSONL])(
                document_with_json_lines
            ),
            "a document Command cannot offer jsonl",
        ),
        (
            command_meta(output="document", formats=[Format.JSON], fields=Fields(("n",), ("n",)))(
                document_with_json_lines
            ),
            "a document Command has no fields",
        ),
        (
            command_meta(output="rows", formats=[Format.JSONL])(rows_without_fields),
            "a rows Command declares its fields",
        ),
        (
            command_meta(
                output="rows", formats=[Format.JSONL, Format.TABLE], fields=Fields(("n",), ("n",))
            )(rows_without_fields),
            "a rows Command cannot offer table",
        ),
        (
            command_meta(output="list", formats=[Format.JSON], fields=Fields(("n",), ("n",)))(
                list_without_cursor
            ),
            "it does not declare cursor; it does not declare fields",
        ),
    ],
)
def test_a_command_its_output_kind_cannot_serve_is_refused(
    command: Callable[..., Any], problem: str
) -> None:
    with pytest.raises(TypeError, match=re.escape(problem)):
        build_app(extra=AppExtra(commands=[command]))


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def table_first(output_format: FormatOpt = Format.TABLE) -> dict[str, Any]:
    return {}


@command_meta(output="list", formats=[Format.JSON], fields=Fields(("n", "sq"), ("n", "size")))
def unavailable_default_field(
    output_format: FormatOpt = Format.JSON,
    limit: int = 50,
    cursor: str | None = None,
    fields: str | None = None,
) -> Any:
    return None


@pytest.mark.parametrize("command", [table_first, unavailable_default_field])
def test_default_format_comes_first_and_default_fields_are_available(
    command: Callable[..., Any],
) -> None:
    with pytest.raises(TypeError, match=command.__name__):
        build_app(extra=AppExtra(commands=[command]))


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def secret_twice(
    output_format: FormatOpt = Format.JSON,
    token: Annotated[
        str | None,
        typer.Option("--token", help="A token."),
        OptionMeta(setting="example.token", secret=True),
    ] = None,
) -> dict[str, Any]:
    return {}


def test_an_option_mapped_to_a_setting_does_not_declare_secret() -> None:
    with pytest.raises(TypeError, match=r"example\.token"):
        build_app(extra=AppExtra(commands=[secret_twice]))


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def short_secret(
    output_format: FormatOpt = Format.JSON,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="A key."),
        OptionMeta(secret=True),
    ] = None,
) -> dict[str, Any]:
    return {}


def test_a_secret_option_with_a_short_name_is_refused() -> None:
    with pytest.raises(TypeError, match="api_key"):
        build_app(extra=AppExtra(commands=[short_secret]))
