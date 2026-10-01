"""Creating a Workspace's files (design D1 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path

from spider import APP_NAME
from spider.workspace.discovery import SETTINGS_FILE_NAME, Workspace

PLACEHOLDER_SETTINGS = (
    f"# {APP_NAME} settings. Precedence: flag, then {SETTINGS_FILE_NAME}, then default.\n"
)


def create_workspace(workspace: Workspace) -> list[Path]:
    gitignore = workspace.data_dir / ".gitignore"
    crawls = workspace.data_dir / "crawls"
    workspace.data_dir.mkdir()
    gitignore.write_bytes(b"")
    crawls.mkdir()
    workspace.settings_file.write_bytes(PLACEHOLDER_SETTINGS.encode())
    return [workspace.data_dir, gitignore, crawls, workspace.settings_file]
