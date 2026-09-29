"""The `temp_workspace` fixture (design D8 of 000-scaffold-project)."""

from pathlib import Path

from tests.support.workspace import TempWorkspace


def test_temp_workspace_is_the_current_folder_under_the_home(
    temp_workspace: TempWorkspace, tmp_path: Path
) -> None:
    assert (Path.cwd(), temp_workspace.root) == (temp_workspace.root, tmp_path / "home" / "work")
