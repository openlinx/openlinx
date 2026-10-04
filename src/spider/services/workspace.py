"""The Workspace service behind `spider init` (design D9 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.output.codes import WORKSPACE_NESTED
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter
from spider.workspace.creation import create_workspace
from spider.workspace.discovery import Workspace, enclosing_workspace, target_workspace
from spider.workspace.tables import SettingsTables
from spider.workspace.template import settings_template


@dataclass(frozen=True)
class InitRequest:
    cwd: Path
    home: Path
    workspace: Path | None = None


@dataclass(frozen=True)
class InitResult:
    workspace: Workspace
    created: list[Path]

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace.root),
            "data_dir": str(self.workspace.data_dir),
            "settings_file": str(self.workspace.settings_file),
            "global": self.workspace.is_global,
            "created": [str(path) for path in self.created],
        }


def init_workspace(request: InitRequest, tables: SettingsTables, reporter: Reporter) -> InitResult:
    # Imported here: pydantic is too heavy for the CLI's startup path.
    from spider.workspace.settings import load_settings

    workspace = target_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    # Loaded only to validate spider.toml, before anything is created.
    load_settings(workspace, tables)
    created = create_workspace(workspace, settings_template(tables))
    parent = enclosing_workspace(workspace, request.home)
    if parent is not None:
        reporter.warn(
            Diagnostic.of(
                WORKSPACE_NESTED,
                f"{workspace.root} is inside the Workspace {parent.root}.",
                hint=f"Commands run below {workspace.root} now use the new Workspace.",
                details={"parent": str(parent.root)},
            )
        )
    return InitResult(workspace, created)
