"""Settings precedence (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from spider.output.diagnostics import SpiderError
from spider.workspace.creation import create_workspace
from spider.workspace.discovery import resolve_workspace, target_workspace
from spider.workspace.settings import load_settings
from spider.workspace.tables import SettingsTables
from spider.workspace.template import settings_template
from tests.support.app import EXAMPLE_TABLE, GROUPS_TABLE, example_app, settings_tables
from tests.support.settings import ExampleSettings
from tests.support.workspace import TempWorkspace


def example_tables() -> SettingsTables:
    tables = SettingsTables()
    tables.register("example", EXAMPLE_TABLE)
    return tables


def workspace_with_data_folder(temp_workspace: TempWorkspace) -> Path:
    shop = temp_workspace.root / "shop"
    (shop / ".spider").mkdir(parents=True)
    return shop


def test_default(temp_workspace: TempWorkspace) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    settings = load_settings(workspace, example_tables())

    assert settings.table(ExampleSettings).level == "low"


def test_settings_file_over_default(temp_workspace: TempWorkspace) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    (shop / "spider.toml").write_bytes(b'[example]\nlevel = "high"\n')
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    settings = load_settings(workspace, example_tables())

    assert settings.table(ExampleSettings).level == "high"


def test_a_settings_file_in_the_home_folder_is_not_read(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(temp_workspace.home)
    notes = temp_workspace.root / "notes"
    notes.mkdir()
    (temp_workspace.home / "spider.toml").write_bytes(b'[example]\nlevel = "high"\n')
    workspace = resolve_workspace(cwd=notes, flag=None, home=temp_workspace.home)

    settings = load_settings(workspace, example_tables())

    assert settings.table(ExampleSettings).level == "low"


def test_flag_over_settings_file(temp_workspace: TempWorkspace) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    (shop / "spider.toml").write_bytes(b'[example]\nlevel = "high"\n')
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    settings = load_settings(workspace, example_tables(), flags={"example": {"level": "low"}})

    assert settings.table(ExampleSettings).level == "low"


def test_setting_variables_are_ignored(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    for name in ("SPIDER_EXAMPLE__LEVEL", "EXAMPLE__LEVEL", "LEVEL"):
        monkeypatch.setenv(name, "high")
    # pydantic-settings' own env source would read this one.
    monkeypatch.setenv("EXAMPLE", '{"level": "high"}')
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    settings = load_settings(workspace, example_tables())

    assert settings.table(ExampleSettings).level == "low"


def test_template_loads_as_defaults(temp_workspace: TempWorkspace) -> None:
    # The tool's tables and the fixture app's: every kind of table, rules' named tables too.
    home, tables = temp_workspace.home, settings_tables(example_app())
    shop = target_workspace(cwd=temp_workspace.root, flag=Path("shop"), home=home)
    create_workspace(shop, settings_template(tables))
    (temp_workspace.root / "empty" / ".spider").mkdir(parents=True)
    empty = resolve_workspace(cwd=temp_workspace.root / "empty", flag=None, home=home)

    from_template = load_settings(shop, tables).root.model_dump()

    assert from_template == load_settings(empty, tables).root.model_dump()


def test_named_entries(temp_workspace: TempWorkspace) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    (shop / "spider.toml").write_bytes(b'[groups.blog]\nlevel = "high"\n')
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    tables = SettingsTables()
    tables.register("groups", GROUPS_TABLE)

    settings = load_settings(workspace, tables)

    assert settings.root.model_dump()["groups"]["blog"]["level"] == "high"


class ListedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field("low", description="The level.")


class ListedSettings(BaseModel):
    """Settings with a list of tables, whose keys the closest-key hint cannot follow."""

    model_config = ConfigDict(extra="forbid")

    entries: list[ListedEntry] = Field([], description="The entries.")
    level: str = Field("low", description="The level.")


def test_a_key_that_cannot_be_followed_keeps_the_hint_of_the_next(
    temp_workspace: TempWorkspace,
) -> None:
    shop = workspace_with_data_folder(temp_workspace)
    (shop / "spider.toml").write_bytes(b'[listed]\nentries = [{levl = "high"}]\nlevl = "high"\n')
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    tables = SettingsTables()
    tables.register("listed", f"{__name__}:ListedSettings")

    with pytest.raises(SpiderError) as raised:
        load_settings(workspace, tables)

    assert raised.value.diagnostic.hint == "Did you mean listed.level?"
