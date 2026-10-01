"""Creating a Workspace's files (design D1 of 010-add-workspace-and-cli-contract)."""

import errno
from pathlib import Path

from spider import APP_NAME
from spider.output.diagnostics import FileSystemError
from spider.workspace.discovery import Workspace

GITIGNORE = f"# Created by {APP_NAME}: crawl data is not committed.\n*\n"


def create_workspace(workspace: Workspace, settings_text: str) -> list[Path]:
    folder, gitignore, crawls, settings = (
        workspace.data_dir,
        workspace.data_dir / ".gitignore",
        workspace.data_dir / "crawls",
        workspace.settings_file,
    )
    created: list[Path] = []
    try:
        workspace.root.mkdir(parents=True, exist_ok=True)
        created += _folder(folder)
        created += _file(gitignore, GITIGNORE)
        created += _folder(crawls)
        created += _file(settings, settings_text)
    except OSError as error:
        raise FileSystemError(
            "workspace_not_writable",
            f"Cannot create or write the Workspace folder {workspace.root}.",
            details={
                "path": str(error.filename or workspace.root),
                "error": errno.errorcode.get(error.errno or 0),
            },
        ) from error
    return created


def _folder(path: Path) -> list[Path]:
    if path.is_dir():
        return []
    path.mkdir()
    return [path]


def _file(path: Path, content: str) -> list[Path]:
    if path.is_file():
        return []
    with path.open("xb") as file:
        file.write(content.encode())
    return [path]
