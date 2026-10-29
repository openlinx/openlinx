"""Creating a Workspace's files (design D1 of 010-add-workspace-and-cli-contract)."""

import errno
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import WORKSPACE_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.workspace.discovery import Workspace

GITIGNORE = f"# Created by {COMMAND_NAME}: crawl data is not committed.\n*\n"


def create_workspace(workspace: Workspace, settings_text: str) -> list[Path]:
    created = create_data_folder(workspace)
    with as_workspace_not_writable(workspace):
        created += _file(workspace.settings_file, settings_text)
    return created


def create_data_folder(workspace: Workspace) -> list[Path]:
    folder = workspace.data_dir
    with as_workspace_not_writable(workspace):
        workspace.root.mkdir(parents=True, exist_ok=True)
        return [
            *_folder(folder),
            *_file(folder / ".gitignore", GITIGNORE),
            *_folder(workspace.crawls_dir),
        ]


@contextmanager
def as_workspace_not_writable(workspace: Workspace) -> Iterator[None]:
    try:
        yield
    except OSError as error:
        raise OpenLinxError(
            WORKSPACE_NOT_WRITABLE,
            f"Cannot create or write the Workspace folder {workspace.root}.",
            details={
                "path": str(error.filename or workspace.root),
                "error": errno.errorcode.get(error.errno or 0),
            },
        ) from error


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
