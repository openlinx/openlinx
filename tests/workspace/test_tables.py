"""What a settings table must be to register (design D2 of 010-add-workspace-and-cli-contract)."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from spider.workspace.tables import SettingsTables, Table


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
        SettingsTables().register("example", table)


def test_a_table_with_toml_defaults_registers() -> None:
    tables = SettingsTables()

    tables.register("example", TomlDefaults)

    assert [name for name, _ in tables.items()] == ["example"]


def test_a_table_name_registers_once() -> None:
    tables = SettingsTables()
    tables.register("example", TomlDefaults)

    with pytest.raises(TypeError):
        tables.register("example", TomlDefaults)
