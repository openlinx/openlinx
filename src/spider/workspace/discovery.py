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
    if flag is not None:
        workspace = target_workspace(cwd=cwd, flag=flag, home=home)
        if not workspace.root.is_dir():
            raise NotFoundError(
                "workspace_not_found",
                f"The Workspace folder {workspace.root} does not exist or is not a folder.",
                hint=f"Create it with: {APP_NAME} init --workspace {workspace.root}",
            )
        return workspace
    cwd, home = cwd.resolve(), home.resolve()
    for folder in (cwd, *cwd.parents):
        if folder == home:
            break
        if (folder / DATA_DIR_NAME).is_dir() or (folder / SETTINGS_FILE_NAME).is_file():
            return _local(folder)
    return _global(home)


def target_workspace(*, cwd: Path, flag: Path | None, home: Path) -> Workspace:
    # Resolved, so `..`, a symlink or a short name that means the home folder still matches it.
    cwd, home = cwd.resolve(), home.resolve()
    root = cwd if flag is None else (cwd / flag).resolve()
    return _global(home) if root == home else _local(root)


def enclosing_workspace(workspace: Workspace, home: Path) -> Workspace | None:
    home = home.resolve()
    if workspace.is_global or home not in workspace.root.parents:
        return None
    parent = resolve_workspace(cwd=workspace.root.parent, flag=None, home=home)
    return None if parent.is_global else parent


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
