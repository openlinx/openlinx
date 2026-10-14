"""Registering Commands on the app (design D7 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable
from typing import Annotated, Any

import pytest
import typer

from spider.cli.app import AppExtra, build_app
from spider.cli.meta import CommandGroup, command_meta
from spider.cli.options import FormatOpt, OptionMeta
from spider.output.paging import Fields
from spider.output.writer import Format


def no_format() -> dict[str, Any]:
    return {}


def document_with_json_lines(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


def rows_without_fields(output_format: FormatOpt = Format.JSONL) -> list[Any]:
    return []


def list_without_cursor(output_format: FormatOpt = Format.JSON, limit: int = 50) -> Any:
    return None


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
        command_meta(output="list", formats=[Format.JSON], fields=Fields(("n",), ("n",)))(
            list_without_cursor
        ),
    ],
)
def test_a_command_its_output_kind_cannot_serve_is_refused(command: Callable[..., Any]) -> None:
    with pytest.raises(TypeError):
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


@command_meta(name="examples show", output="document", formats=[Format.JSON])
def grouped(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


@command_meta(name="examples list", output="document", formats=[Format.JSON])
def other_grouped(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


def test_a_command_named_outside_its_group_is_refused() -> None:
    group = CommandGroup(name="others", summary="Others.", commands=(grouped,), default=grouped)

    with pytest.raises(TypeError, match="not named under others"):
        build_app(AppExtra(commands=[group]))


def test_a_group_whose_default_is_not_one_of_its_commands_is_refused() -> None:
    group = CommandGroup(
        name="examples", summary="Examples.", commands=(grouped,), default=other_grouped
    )

    with pytest.raises(TypeError, match="default"):
        build_app(AppExtra(commands=[group]))


@command_meta(name="two words", output="document", formats=[Format.JSON])
def spaced(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    return {}


def test_a_top_level_command_name_with_a_space_is_refused() -> None:
    with pytest.raises(TypeError, match="space"):
        build_app(AppExtra(commands=[spaced]))


@pytest.mark.parametrize("name", ["init", "rules"])
def test_a_group_name_already_taken_is_refused(name: str) -> None:
    @command_meta(name=f"{name} other", output="document", formats=[Format.JSON])
    def other(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
        return {}

    group = CommandGroup(name=name, summary="Taken.", commands=(other,), default=other)

    with pytest.raises(TypeError, match="named"):
        build_app(AppExtra(commands=[group]))


def test_a_group_name_with_a_space_is_refused() -> None:
    @command_meta(name="two words list", output="document", formats=[Format.JSON])
    def listed(output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
        return {}

    group = CommandGroup(name="two words", summary="Two.", commands=(listed,), default=listed)

    with pytest.raises(TypeError, match="space"):
        build_app(AppExtra(commands=[group]))
