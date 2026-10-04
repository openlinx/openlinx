"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

import inspect
from enum import Enum
from typing import Any, cast

import typer
from typer.core import TyperGroup

from spider import APP_NAME, __version__
from spider.cli.meta import CommandMeta, Example, command_meta, meta_of
from spider.cli.options import FormatOpt, option_meta
from spider.output.codes import DECLARED, ExitCode
from spider.output.writer import Format

# The only variables the tool honours: the OS's proxy settings, which 022 applies to fetching.
ENVIRONMENT = [
    {
        "names": ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"],
        "description": "The proxy for fetching, matched in any letter case. "
        "--proxy or [crawl] proxy overrides them.",
    }
]


@command_meta(
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[Example(f"{APP_NAME} commands", "Describe every Command.")],
)
def commands(ctx: typer.Context, output_format: FormatOpt = Format.JSON) -> dict[str, Any]:
    """Describe every Command as JSON.

    Lists every Command with its output kind, formats, arguments, options and fields, then the
    exit codes, every diagnostic code and the environment variables the tool honours. It needs
    no Workspace.
    """
    root = cast(TyperGroup, ctx.find_root().command)
    return {
        "tool": {"name": APP_NAME, "version": __version__},
        "commands": [_entry(name, root.commands[name]) for name in sorted(root.commands)],
        "exit_codes": [
            {"code": code.value, "name": code.name.lower(), "description": code.description}
            for code in ExitCode
        ],
        "diagnostics": [
            {
                "code": declared.code,
                "level": declared.level,
                "exit_code": None if declared.exit_code is None else declared.exit_code.value,
                "description": declared.description,
            }
            for declared in DECLARED
        ],
        "environment": ENVIRONMENT,
    }


def _entry(name: str, command: Any) -> dict[str, Any]:
    # build_app refuses a Command without @command_meta, so every entry has one.
    meta = cast(CommandMeta, meta_of(command.callback))
    # Source line breaks are not content: each paragraph becomes one line.
    paragraphs = (inspect.getdoc(inspect.unwrap(command.callback)) or "").split("\n\n")
    doc = "\n\n".join(" ".join(paragraph.split()) for paragraph in paragraphs)
    return {
        "name": name,
        "summary": doc.partition("\n")[0],
        "description": doc,
        "output": meta.output,
        "events": meta.events,
        "formats": list(meta.formats),
        "arguments": _arguments(command),
        "options": _options(command, meta),
        "fields": None
        if meta.fields is None
        else {"available": list(meta.fields.available), "default": list(meta.fields.default)},
        "examples": [
            {"command": example.command, "description": example.description}
            for example in meta.examples
        ],
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
