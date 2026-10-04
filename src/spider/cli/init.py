"""`spider init` (design D1 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Any

import typer

from spider.cli.meta import command_meta
from spider.cli.options import FormatOpt, WorkspaceOpt
from spider.cli.runner import Invocation
from spider.output.codes import WORKSPACE_NESTED
from spider.output.diagnostics import Diagnostic
from spider.output.writer import Format
from spider.workspace.creation import create_workspace
from spider.workspace.discovery import enclosing_workspace, target_workspace
from spider.workspace.template import settings_template


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def init(
    ctx: typer.Context, workspace_dir: WorkspaceOpt = None, output_format: FormatOpt = Format.JSON
) -> dict[str, Any]:
    """Make the current folder, or the --workspace folder, a Workspace."""
    # Imported here: pydantic is too heavy for the CLI's startup path.
    from spider.workspace.settings import load_settings

    invocation: Invocation = ctx.obj
    home = Path.home()
    workspace = target_workspace(cwd=Path.cwd(), flag=workspace_dir, home=home)
    # Loaded only to validate spider.toml, before anything is created.
    load_settings(workspace, invocation.settings_tables)
    created = create_workspace(workspace, settings_template(invocation.settings_tables))
    parent = enclosing_workspace(workspace, home)
    if parent is not None:
        invocation.reporter.warn(
            Diagnostic.of(
                WORKSPACE_NESTED,
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
