"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

from typing import Any, cast

import typer
from typer.core import TyperGroup

from spider import APP_NAME, __version__
from spider.cli.meta import command_meta
from spider.output.diagnostics import EXIT_CODE_DESCRIPTIONS


@command_meta(output="document")
def commands(ctx: typer.Context) -> dict[str, Any]:
    """Describe every Command as JSON."""
    root = cast(TyperGroup, ctx.find_root().command)
    return {
        "tool": {"name": APP_NAME, "version": __version__},
        "commands": [{"name": name} for name in sorted(root.commands)],
        "exit_codes": [
            {"code": code.value, "name": code.name.lower(), "description": description}
            for code, description in EXIT_CODE_DESCRIPTIONS.items()
        ],
    }
