"""Settings precedence (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

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
