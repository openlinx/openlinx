"""`spider init` over the Workspace service (design D9 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path
from typing import Any

import typer

from spider import APP_NAME
from spider.cli.meta import Example, command_meta
from spider.cli.options import FormatOpt, WorkspaceOpt
from spider.cli.runner import Invocation
from spider.output.writer import Format
from spider.services.workspace import InitRequest, init_workspace


@command_meta(
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[
        Example(f"{APP_NAME} init", "Make the current folder a Workspace."),
        Example(
            f"{APP_NAME} init --workspace site", "Create the folder site and make it a Workspace."
        ),
    ],
)
def init(
    ctx: typer.Context, workspace_dir: WorkspaceOpt = None, output_format: FormatOpt = Format.JSON
) -> dict[str, Any]:
    """Make the current folder, or the --workspace folder, a Workspace.

    Creates only what is missing: the data folder with its .gitignore and crawls folder, and a
    commented settings file. It never changes an existing file, and it checks an existing
    settings file first.
    """
    invocation: Invocation = ctx.obj
    request = InitRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir)
    return init_workspace(request, invocation.settings_tables, invocation.reporter).to_json()
