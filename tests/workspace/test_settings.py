"""Settings precedence (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

import pytest

from spider.workspace.discovery import resolve_workspace
from spider.workspace.settings import load_settings
from spider.workspace.tables import SettingsTables
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
