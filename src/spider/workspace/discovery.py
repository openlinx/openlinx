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
    is_global: bool


def resolve_workspace(*, cwd: Path, flag: Path | None, home: Path) -> Workspace:
    for folder in (cwd, *cwd.parents):
        if folder == home:
            break
        if (folder / DATA_DIR_NAME).is_dir() or (folder / SETTINGS_FILE_NAME).is_file():
            return Workspace(root=folder, data_dir=folder / DATA_DIR_NAME, is_global=False)
    return Workspace(root=home, data_dir=home / DATA_DIR_NAME, is_global=True)
