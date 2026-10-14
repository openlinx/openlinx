"""`spider commands`, the self-description (design D7 of 010-add-workspace-and-cli-contract)."""

import inspect
from collections.abc import Callable
from enum import Enum
from pathlib import PurePath
from typing import Any, cast

import typer
from typer.core import TyperArgument, TyperGroup

from spider import __version__
from spider.cli.click_compat import Command, Parameter
from spider.cli.meta import CommandMeta, Example, command_meta, meta_of
from spider.cli.options import FORMAT_PARAMETER, FormatOpt, is_secret_option, options_with_meta
from spider.cli.runner import Invocation
from spider.naming import APP_NAME
from spider.output.codes import DECLARED, ExitCode
from spider.output.writer import Format
from spider.workspace.tables import SettingsTables

# Click's type names, in the words of JSON Schema where they differ.
TYPE_NAMES = {
    "str": "string",
    "int": "integer",
    "int range": "integer",
    "float": "number",
    "float range": "number",
}

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
    invocation: Invocation = ctx.obj
    return {
        "tool": {"name": APP_NAME, "version": __version__},
        "commands": [
            _entry(name, command, invocation.settings_tables)
            for name, command in sorted(root.commands.items())
            # Hidden Commands are not part of the contract: --help does not show them either.
            if not command.hidden
        ],
        "exit_codes": [
            {"code": code.value, "name": code.name.lower(), "description": code.description}
            for code in ExitCode
        ],
        "diagnostics": [declared.to_json() for declared in DECLARED],
        "environment": ENVIRONMENT,
    }


def _entry(name: str, command: Command, tables: SettingsTables) -> dict[str, Any]:
    # build_app refuses a Command without @command_meta, so every entry has a callback with one.
    callback = cast(Callable[..., Any], command.callback)
    meta = cast(CommandMeta, meta_of(callback))
    # Source line breaks are not content: each paragraph becomes one line.
    paragraphs = (inspect.getdoc(inspect.unwrap(callback)) or "").split("\n\n")
    doc = "\n\n".join(" ".join(paragraph.split()) for paragraph in paragraphs)
    return {
        "name": name,
        "summary": doc.partition("\n")[0],
        "description": doc,
        "output": meta.output,
        "events": meta.events,
        "formats": list(meta.formats),
        "arguments": _arguments(command),
        "options": _options(command, meta, tables),
        "fields": None if meta.fields is None else meta.fields.to_json(),
        "examples": [example.to_json() for example in meta.examples],
    }


def _arguments(command: Command) -> list[dict[str, Any]]:
    return [
        {
            "name": param.name,
            "type": _type(param),
            "required": param.required,
            "variadic": param.nargs == -1,
            "default": _json_value(param.default),
            "description": param.help,
        }
        for param in command.params
        if isinstance(param, TyperArgument)
    ]


def _options(command: Command, meta: CommandMeta, tables: SettingsTables) -> list[dict[str, Any]]:
    entries = []
    for param, extra in options_with_meta(command):
        choices = getattr(param.type, "choices", None)
        if param.name == FORMAT_PARAMETER:
            # Click knows every format; the Command offers only its own.
            choices = meta.formats
        entries.append(
            {
                "name": _long_name(param),
                "short": next((opt for opt in param.opts if len(opt) == 2), None),
                "type": _type(param),
                "choices": None if choices is None else [_json_value(c) for c in choices],
                # A repeatable option given no value is empty, as Click passes it.
                "default": []
                if param.multiple and param.default is None
                else _json_value(param.default),
                "required": param.required,
                "multiple": param.multiple,
                "global": extra.is_global,
                "setting": extra.setting,
                "secret": is_secret_option(extra, tables),
                "description": param.help,
            }
        )
    return entries


def _type(param: Parameter) -> str:
    name = str(param.type.name)
    return TYPE_NAMES.get(name, name)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    # The same text on every OS, never a path made absolute on this machine.
    return value.as_posix() if isinstance(value, PurePath) else value


def _long_name(param: Parameter) -> str:
    return str(max(param.opts, key=len))
