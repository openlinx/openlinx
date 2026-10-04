"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

from enum import Enum
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
        "arguments": _arguments(command),
        "options": _options(command, meta),
        "fields": None
        if meta.fields is None
        else {"available": list(meta.fields.available), "default": list(meta.fields.default)},
    }


def _arguments(command: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": param.name,
            "type": _type(param),
            "required": param.required,
            "variadic": param.nargs == -1,
            "default": _json_value(param.default),
            "description": getattr(param, "help", None),
        }
        for param in command.params
        if param.param_type_name == "argument"
    ]


def _options(command: Any, meta: CommandMeta) -> list[dict[str, Any]]:
    entries = []
    for param in command.params:
        if param.param_type_name != "option":
            continue
        extra = option_meta(command.callback, param.name)
        choices = getattr(param.type, "choices", None)
        if param.name == "output_format":
            # Click knows every format; the Command offers only its own.
            choices = meta.formats
        entries.append(
            {
                "name": _long_name(param),
                "short": next((opt for opt in param.opts if len(opt) == 2), None),
                "type": _type(param),
                "choices": None if choices is None else [_json_value(c) for c in choices],
                "default": _json_value(param.default),
                "required": param.required,
                "multiple": param.multiple,
                "global": extra.is_global,
                "setting": extra.setting,
                "secret": extra.secret,
                "description": param.help,
            }
        )
    return entries


# Click's type names, in the words of JSON Schema where they differ.
TYPE_NAMES = {"text": "string", "integer range": "integer", "float": "number"}


def _type(param: Any) -> str:
    name = str(param.type.name)
    return TYPE_NAMES.get(name, name)


def _json_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _long_name(param: Any) -> str:
    return str(max(param.opts, key=len))
