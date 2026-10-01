"""Finding the Workspace (010-add-workspace-and-cli-contract, workspace)."""

from spider.workspace.discovery import resolve_workspace
from tests.support.workspace import TempWorkspace


def test_workspace_in_the_current_folder(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / ".spider").mkdir(parents=True)

    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    assert workspace.root == shop
