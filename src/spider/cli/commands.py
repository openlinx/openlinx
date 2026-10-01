"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

from typing import Any, cast

import typer
from typer.core import TyperGroup

from spider.cli.meta import command_meta


@command_meta(output="document")
def commands(ctx: typer.Context) -> dict[str, Any]:
    """Describe every Command as JSON."""
    root = cast(TyperGroup, ctx.find_root().command)
    return {"commands": [{"name": name} for name in sorted(root.commands)]}
