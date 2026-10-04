"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

from typing import Any, cast

import typer
from typer.core import TyperGroup

from spider import APP_NAME, __version__
from spider.cli.meta import CommandMeta, command_meta, meta_of
from spider.cli.options import FormatOpt, option_meta
from spider.output.diagnostics import EXIT_CODE_DESCRIPTIONS
from spider.output.writer import Format


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def commands(ctx: typer.Context, output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    """Describe every Command as JSON."""
    root = cast(TyperGroup, ctx.find_root().command)
    return {
        "tool": {"name": APP_NAME, "version": __version__},
        "commands": [_entry(name, root.commands[name]) for name in sorted(root.commands)],
        "exit_codes": [
            {"code": code.value, "name": code.name.lower(), "description": description}
            for code, description in EXIT_CODE_DESCRIPTIONS.items()
        ],
    }


def _entry(name: str, command: Any) -> dict[str, Any]:
    # build_app refuses a Command without @command_meta, so every entry has one.
    meta = cast(CommandMeta, meta_of(command.callback))
    return {
        "name": name,
        "output": meta.output,
        "events": meta.events,
        "formats": list(meta.formats),
        "options": _options(command),
        "fields": None
        if meta.fields is None
        else {"available": list(meta.fields.available), "default": list(meta.fields.default)},
    }


def _options(command: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": _long_name(param),
            "global": option_meta(command.callback, param.name).is_global,
        }
        for param in command.params
        if param.param_type_name == "option"
    ]


def _long_name(param: Any) -> str:
    return str(max(param.opts, key=len))
