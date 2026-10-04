"""The table rules and the registry (design D2 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Callable
from typing import cast

import pytest
import typer
from pydantic import BaseModel, ConfigDict, Field

from spider.cli.app import build_app
from spider.cli.runner import SpiderGroup
from spider.workspace.tables import SettingsTables, Table, check_table
from tests.support.app import example_app


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
    "table",
    [
        Loose,
        Undescribed,
        TwoLineDescription,
        NotANumberDefault,
        dict[str, Loose],
        dict[int, TomlDefaults],
        dict[str, TomlDefaults],
    ],
)
def test_a_table_the_template_cannot_describe_is_refused(table: Table) -> None:
    with pytest.raises(TypeError):
        check_table("example", table)


@pytest.mark.parametrize("table", [TomlDefaults, dict[str, str]])
def test_a_table_with_toml_defaults_follows_the_rules(table: Table) -> None:
    check_table("example", table)


@pytest.mark.parametrize("app", [build_app, example_app])
def test_every_registered_table_follows_the_rules(app: Callable[[], typer.Typer]) -> None:
    tables = cast(SpiderGroup, typer.main.get_group(app())).settings_tables

    for name, table in tables.items():
        check_table(name, table)


def test_a_table_resolves_from_its_reference() -> None:
    tables = SettingsTables()

    tables.register("example", f"{__name__}:TomlDefaults")

    assert list(tables.items()) == [("example", TomlDefaults)]


def test_a_table_name_registers_once() -> None:
    tables = SettingsTables()
    tables.register("example", f"{__name__}:TomlDefaults")

    with pytest.raises(TypeError):
        tables.register("example", f"{__name__}:TomlDefaults")
