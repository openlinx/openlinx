"""Finding the Workspace (design D1 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path


def resolve_workspace(*, cwd: Path, flag: Path | None, home: Path) -> Workspace:
    for folder in (cwd, *cwd.parents):
        if folder == home:
            break
        if (folder / ".spider").is_dir():
            return Workspace(root=folder)
    return Workspace(root=cwd)
