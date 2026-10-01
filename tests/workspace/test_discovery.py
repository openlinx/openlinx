"""Finding the Workspace (010-add-workspace-and-cli-contract, workspace)."""

from spider.workspace.discovery import resolve_workspace
from tests.support.workspace import TempWorkspace


def test_workspace_in_the_current_folder(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / ".spider").mkdir(parents=True)

    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_workspace_in_a_parent_folder(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / ".spider").mkdir(parents=True)
    (shop / "blog").mkdir()

    workspace = resolve_workspace(cwd=shop / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_the_nearest_workspace_wins(temp_workspace: TempWorkspace) -> None:
    work = temp_workspace.home / "work"
    (work / ".spider").mkdir()
    (work / "shop" / ".spider").mkdir(parents=True)
    (work / "shop" / "blog").mkdir()

    workspace = resolve_workspace(cwd=work / "shop" / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == work / "shop"


def test_a_settings_file_alone_marks_a_workspace(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / "blog").mkdir(parents=True)
    (shop / "spider.toml").write_text("", encoding="utf-8")

    workspace = resolve_workspace(cwd=shop / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_fallback_to_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.home / "work" / "notes"
    notes.mkdir(parents=True)

    workspace = resolve_workspace(cwd=notes, flag=None, home=temp_workspace.home)

    assert (workspace.is_global, workspace.data_dir) == (True, temp_workspace.home / ".spider")
