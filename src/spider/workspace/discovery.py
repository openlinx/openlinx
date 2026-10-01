"""Finding the Workspace (design D1 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path

from spider import APP_NAME

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
        return _local(cwd / flag)
    for folder in (cwd, *cwd.parents):
        if folder == home:
            break
        if (folder / DATA_DIR_NAME).is_dir() or (folder / SETTINGS_FILE_NAME).is_file():
            return _local(folder)
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
