"""Creating a Workspace's files (design D1 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path

from spider import APP_NAME
from spider.workspace.discovery import SETTINGS_FILE_NAME, Workspace

GITIGNORE = f"# Created by {APP_NAME}: crawl data is not committed.\n*\n"
PLACEHOLDER_SETTINGS = (
    f"# {APP_NAME} settings. Precedence: flag, then {SETTINGS_FILE_NAME}, then default.\n"
)


def create_workspace(workspace: Workspace) -> list[Path]:
    entries: list[tuple[Path, str | None]] = [
        (workspace.data_dir, None),
        (workspace.data_dir / ".gitignore", GITIGNORE),
        (workspace.data_dir / "crawls", None),
        (workspace.settings_file, PLACEHOLDER_SETTINGS),
    ]
    workspace.root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for path, content in entries:
        if path.exists():
            continue
        if content is None:
            path.mkdir()
        else:
            with path.open("xb") as file:
                file.write(content.encode())
        created.append(path)
    return created
