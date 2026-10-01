"""Settings precedence (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

import pytest

from spider.workspace.creation import create_workspace
from spider.workspace.discovery import resolve_workspace, target_workspace
from spider.workspace.settings import load_settings
from spider.workspace.tables import SettingsTables
from spider.workspace.template import settings_template
from tests.support.settings import ExampleSettings
from tests.support.workspace import TempWorkspace


def example_tables() -> SettingsTables:
    tables = SettingsTables()
    tables.register("example", ExampleSettings)
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


def test_a_settings_file_in_the_home_folder_is_not_read(temp_workspace: TempWorkspace) -> None:
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
    home, tables = temp_workspace.home, example_tables()
    shop = target_workspace(cwd=temp_workspace.root, flag=Path("shop"), home=home)
    create_workspace(shop, settings_template(tables))
    (temp_workspace.root / "empty" / ".spider").mkdir(parents=True)
    empty = resolve_workspace(cwd=temp_workspace.root / "empty", flag=None, home=home)

    from_template = load_settings(shop, tables).root.model_dump()

    assert from_template == load_settings(empty, tables).root.model_dump()
