"""`spider init` (design D1 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Any

from spider.cli.meta import command_meta
from spider.cli.options import FormatOpt, WorkspaceOpt
from spider.output.writer import Format
from spider.workspace.creation import create_workspace
from spider.workspace.discovery import workspace_at


@command_meta(formats=[Format.JSON, Format.TABLE])
def init(
    workspace_dir: WorkspaceOpt = None, output_format: FormatOpt = Format.JSON
) -> dict[str, Any]:
    """Make the current folder, or the --workspace folder, a Workspace."""
    target = Path.cwd() if workspace_dir is None else Path.cwd() / workspace_dir
    workspace = workspace_at(target.resolve(), Path.home().resolve())
    created = create_workspace(workspace)
    return {
        "workspace": str(workspace.root),
        "data_dir": str(workspace.data_dir),
        "settings_file": str(workspace.settings_file),
        "global": workspace.is_global,
        "created": [str(path) for path in created],
    }
