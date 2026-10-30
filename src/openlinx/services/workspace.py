"""The Workspace service behind `linx init` (design D9 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openlinx.output.codes import WORKSPACE_NESTED
from openlinx.output.diagnostics import Diagnostic
from openlinx.output.reporter import Reporter
from openlinx.services.settings import default_tables
from openlinx.workspace.creation import create_workspace
from openlinx.workspace.discovery import Workspace, enclosing_workspace, target_workspace
from openlinx.workspace.tables import SettingsTables
from openlinx.workspace.template import settings_template


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


def init_workspace(
    request: InitRequest, reporter: Reporter, tables: SettingsTables | None = None
) -> InitResult:
    """`tables` are the built-in ones unless given."""
    # Imported here: pydantic is too heavy for the CLI's startup path.
    from openlinx.workspace.settings import load_settings

    tables = tables or default_tables()
    workspace = target_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    # Loaded only to validate the settings file, before anything is created.
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
