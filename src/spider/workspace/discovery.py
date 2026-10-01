"""Finding the Workspace (design D1 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path


def resolve_workspace(*, cwd: Path, flag: Path | None, home: Path) -> Workspace:
    return Workspace(root=cwd)
