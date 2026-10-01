"""Finding the Workspace (design D1 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path

from spider import APP_NAME
from spider.output.diagnostics import NotFoundError

DATA_DIR_NAME = f".{APP_NAME}"
SETTINGS_FILE_NAME = f"{APP_NAME}.toml"


@dataclass(frozen=True)
class Workspace:
    root: Path
    data_dir: Path
    settings_file: Path
    is_global: bool


def resolve_workspace(*, cwd: Path, flag: Path | None, home: Path) -> Workspace:
    # Resolved, so `..`, a symlink or a short name that means the home folder still matches it.
    cwd, home = cwd.resolve(), home.resolve()
    if flag is not None:
        root = (cwd / flag).resolve()
        if not root.is_dir():
            raise NotFoundError(
                "workspace_not_found",
                f"The Workspace folder {root} does not exist or is not a folder.",
                hint=f"Create it with: {APP_NAME} init --workspace {root}",
            )
        return workspace_at(root, home)
    for folder in (cwd, *cwd.parents):
        if folder == home:
            break
        if (folder / DATA_DIR_NAME).is_dir() or (folder / SETTINGS_FILE_NAME).is_file():
            return _local(folder)
    return _global(home)


def enclosing_workspace(workspace: Workspace, home: Path) -> Workspace | None:
    if workspace.is_global:
        return None
    parent = resolve_workspace(cwd=workspace.root.parent, flag=None, home=home)
    return None if parent.is_global else parent


def workspace_at(root: Path, home: Path) -> Workspace:
    return _global(home) if root == home else _local(root)


def _global(home: Path) -> Workspace:
    return Workspace(
        root=home,
        data_dir=home / DATA_DIR_NAME,
        settings_file=home / DATA_DIR_NAME / SETTINGS_FILE_NAME,
        is_global=True,
    )


def _local(root: Path) -> Workspace:
    return Workspace(
        root=root,
        data_dir=root / DATA_DIR_NAME,
        settings_file=root / SETTINGS_FILE_NAME,
        is_global=False,
    )
