"""Verify settings table registration and the table contract."""

import re
from collections.abc import Callable
from typing import Annotated, cast

import pytest
import typer
from pydantic import BaseModel, ConfigDict, Field

from openlinx.cli.app import AppExtra, build_app
from openlinx.cli.meta import CommandGroup, command_meta
from openlinx.cli.options import FormatOpt, OptionMeta, options_with_meta
from openlinx.cli.runner import OpenLinxGroup, commands_by_path
from openlinx.output.writer import Format
from openlinx.workspace.tables import SettingsTables, Table, check_table
from tests.support.app import EXAMPLE_TABLE, example_app


class Loose(BaseModel):
    level: str = Field("low", description="A level.")


class Undescribed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "low"


class TwoLineDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field("low", description="A level.\nOn two lines.")


class NotANumberDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ratio: float = Field(float("nan"), description="A ratio.")


class TomlDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ratio: float = Field(0.5, description="A ratio.")
    hosts: list[str] = Field(["a", "b"], description="Some hosts.")
    proxy: str | None = Field(None, description="A proxy, unset by default.")


@pytest.mark.parametrize(
    ("table", "problem"),
    [
        (Loose, 'Settings table [example] must set extra="forbid"'),
        (Undescribed, "Setting example.level needs a one-line description"),
        (TwoLineDescription, "Setting example.level needs a one-line description"),
        (NotANumberDefault, "Setting example.ratio needs a default TOML can write"),
        (dict[str, Loose], 'Settings table [example.<name>] must set extra="forbid"'),
        (dict[int, TomlDefaults], "A keyed settings table needs str keys"),
        (dict[str, TomlDefaults], "Settings table [example] needs a one-line entry docstring"),
        (dict[str, str], "Settings table [example] needs a table model for its entries"),
    ],
)
def test_a_table_the_template_cannot_describe_is_refused(table: Table, problem: str) -> None:
    with pytest.raises(TypeError, match=re.escape(problem)):
        check_table("example", table)


def test_a_table_with_toml_defaults_follows_the_rules() -> None:
    check_table("example", TomlDefaults)


@pytest.mark.parametrize("app", [build_app, example_app])
def test_every_registered_table_follows_the_rules(app: Callable[[], typer.Typer]) -> None:
    tables = cast(OpenLinxGroup, typer.main.get_group(app())).settings_tables

    for name, table in tables.items():
        check_table(name, table)


@pytest.mark.parametrize("app", [build_app, example_app])
def test_every_option_setting_names_a_setting_of_a_registered_table(
    app: Callable[[], typer.Typer],
) -> None:
    assert _missing_option_settings(app()) == [], (
        "an option's OptionMeta(setting=...) names no registered setting: fix its key"
    )


def _missing_option_settings(app: typer.Typer) -> list[str]:
    group = cast(OpenLinxGroup, typer.main.get_group(app))
    tables = dict(group.settings_tables.items())
    settings = (
        extra.setting
        for _, command in commands_by_path(group, include_hidden=True)
        for _, extra in options_with_meta(command)
        if extra.setting is not None
    )
    return [
        setting
        for setting in settings
        if not _names_a_flat_setting(tables, *setting.partition(".")[::2])
    ]


@pytest.mark.parametrize("app", [build_app, example_app])
def test_options_of_secret_settings_have_only_long_names(app: Callable[[], typer.Typer]) -> None:
    assert _short_secret_options(app()) == [], (
        "an option of a secret setting has a short name: give it only its long name"
    )


def _short_secret_options(app: typer.Typer) -> list[tuple[str, str]]:
    group = cast(OpenLinxGroup, typer.main.get_group(app))
    tables = group.settings_tables
    return [
        (path, name)
        for path, command in commands_by_path(group, include_hidden=True)
        for option, extra in options_with_meta(command)
        if extra.setting is not None and tables.is_secret(extra.setting)
        for name in option.opts
        if not name.startswith("--")
    ]


def _app_with_grouped_option(setting: str, *option_names: str) -> typer.Typer:
    @command_meta(name="example check", output="document", formats=[Format.JSON])
    def check(
        output_format: FormatOpt = Format.JSON,
        option: Annotated[
            str | None, typer.Option(*option_names), OptionMeta(setting=setting)
        ] = None,
    ) -> dict[str, str]:
        return {}

    group = CommandGroup(
        name="example", summary="Check a setting-backed option.", commands=(check,), default=check
    )
    return build_app(extra=AppExtra(settings_tables={"example": EXAMPLE_TABLE}, commands=[group]))


def test_a_grouped_option_must_name_a_registered_setting() -> None:
    app = _app_with_grouped_option("example.absent", "--absent")

    assert _missing_option_settings(app) == ["example.absent"]


def test_a_grouped_option_inherits_the_secret_setting_rule() -> None:
    app = _app_with_grouped_option("example.token", "--token", "-t")

    assert _short_secret_options(app) == [("example check", "-t")]


def _names_a_flat_setting(tables: dict[str, Table], name: str, key: str) -> bool:
    table = tables.get(name)
    # A keyed table has no model_fields: its settings sit inside named entries.
    return key in getattr(table, "model_fields", {})


def test_a_table_resolves_from_its_reference() -> None:
    tables = SettingsTables()

    tables.register("example", f"{__name__}:TomlDefaults")

    assert list(tables.items()) == [("example", TomlDefaults)]


def test_a_table_name_registers_once() -> None:
    tables = SettingsTables()
    tables.register("example", f"{__name__}:TomlDefaults")

    with pytest.raises(TypeError):
        tables.register("example", f"{__name__}:TomlDefaults")
