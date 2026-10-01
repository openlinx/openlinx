"""`spider init` (design D1 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Any

import typer

from spider.cli.meta import command_meta
from spider.cli.options import FormatOpt, WorkspaceOpt
from spider.output.diagnostics import Diagnostic
from spider.output.writer import Format, Output
from spider.workspace.creation import create_workspace
from spider.workspace.discovery import enclosing_workspace, workspace_at


@command_meta(formats=[Format.JSON, Format.TABLE])
def init(
    ctx: typer.Context, workspace_dir: WorkspaceOpt = None, output_format: FormatOpt = Format.JSON
) -> dict[str, Any]:
    """Make the current folder, or the --workspace folder, a Workspace."""
    output: Output = ctx.obj
    home = Path.home().resolve()
    target = Path.cwd() if workspace_dir is None else Path.cwd() / workspace_dir
    workspace = workspace_at(target.resolve(), home)
    created = create_workspace(workspace)
    parent = enclosing_workspace(workspace, home)
    if parent is not None:
        output.diagnostic(
            Diagnostic(
                "warning",
                "workspace_nested",
                f"{workspace.root} is inside the Workspace {parent.root}.",
                hint=f"Commands run below {workspace.root} now use the new Workspace.",
                details={"parent": str(parent.root)},
            )
        )
    return {
        "workspace": str(workspace.root),
        "data_dir": str(workspace.data_dir),
        "settings_file": str(workspace.settings_file),
        "global": workspace.is_global,
        "created": [str(path) for path in created],
    }
