"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from spider.cli.options import FORMAT_PARAMETER, option_meta, option_names
from spider.output.codes import INVALID_VALUE, MORE_ITEMS
from spider.output.diagnostics import Diagnostic, Outcome, SpiderError
from spider.output.paging import Fields, Page
from spider.output.writer import Document, Format, Rows

type OutputKind = Literal["document", "list", "rows"]


@dataclass(frozen=True)
class Example:
    command: str
    description: str

    def to_json(self) -> dict[str, Any]:
        return {"command": self.command, "description": self.description}


@dataclass(frozen=True)
class CommandMeta:
    name: str
    output: OutputKind
    formats: tuple[Format, ...]
    fields: Fields | None
    events: bool
    examples: tuple[Example, ...]


# What each output kind can serve, and the parameters every Command of the kind declares.
KIND_FORMATS: Mapping[OutputKind, frozenset[Format]] = {
    "document": frozenset({Format.JSON, Format.TABLE}),
    "list": frozenset({Format.JSON, Format.JSONL, Format.TABLE}),
    "rows": frozenset({Format.JSONL}),
}
KIND_PARAMETERS: Mapping[OutputKind, tuple[str, ...]] = {
    "document": (FORMAT_PARAMETER,),
    "list": (FORMAT_PARAMETER, "limit", "cursor", "fields"),
    "rows": (FORMAT_PARAMETER,),
}


def command_meta[**P](
    *,
    output: OutputKind,
    formats: Sequence[Format],
    fields: Fields | None = None,
    events: bool = False,
    name: str | None = None,
    examples: Sequence[Example] = (),
) -> Callable[[Callable[P, Any]], Callable[P, Document | Rows]]:
    def decorate(command: Callable[P, Any]) -> Callable[P, Document | Rows]:
        # The one name of the Command: registration, spider commands, cursors and MCP use it.
        meta = CommandMeta(
            name or command.__name__.replace("_", "-"),
            output,
            tuple(formats),
            fields,
            events,
            tuple(examples),
        )

        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> Document | Rows:
            output_format = cast(Format, kwargs[FORMAT_PARAMETER])
            if output_format not in meta.formats:
                raise SpiderError(
                    INVALID_VALUE,
                    f"This Command has no {output_format} format.",
                    hint=formats_hint(meta),
                )
            result = command(*args, **kwargs)
            if meta.fields is None:
                if isinstance(result, Outcome):
                    return Document(result.result, output_format, "document", error=result.error)
                return Document(result, output_format, "document")
            if meta.output == "rows":
                return Rows(result, output_format)
            return Document(
                _envelope(result), output_format, "list", _more_items(result, output_format)
            )

        run.command_meta = meta  # type: ignore[attr-defined]
        return run

    return decorate


def meta_of(command: Callable[..., Any]) -> CommandMeta | None:
    meta: CommandMeta | None = getattr(command, "command_meta", None)
    return meta


def check_command(command: Callable[..., Any]) -> CommandMeta:
    meta = meta_of(command)
    if meta is None:
        raise TypeError(f"Command {command.__name__} has no @command_meta.")
    declared = inspect.signature(command).parameters
    problems = [
        f"it does not declare {name}"
        for name in KIND_PARAMETERS[meta.output]
        if name not in declared
    ]
    problems += [
        f"a {meta.output} Command cannot offer {format_}"
        for format_ in meta.formats
        if format_ not in KIND_FORMATS[meta.output]
    ]
    default_format = declared.get(FORMAT_PARAMETER)
    if default_format is not None and (default_format.default,) != meta.formats[:1]:
        problems.append("its --format default is not the first of its formats")
    problems += [
        f"{name} declares secret, which its setting {extra.setting} decides"
        for name in declared
        if (extra := option_meta(command, name)).setting is not None and extra.secret
    ]
    # The attached short form (-tVALUE) would slip past redaction (design D7 of 015).
    problems += [
        f"{name} is secret, so it cannot have the short name {short}"
        for name in declared
        if option_meta(command, name).secret
        for short in option_names(command, name)
        if not short.startswith("--")
    ]
    if (meta.output == "document") != (meta.fields is None):
        problems.append("fields belong to list and rows Commands only")
    elif meta.fields is not None and not set(meta.fields.default) <= set(meta.fields.available):
        problems.append("its default fields are not all available")
    if problems:
        raise TypeError(f"Command {command.__name__}: {'; '.join(problems)}.")
    return meta


def formats_hint(meta: CommandMeta) -> str:
    return f"Use --format with one of: {', '.join(meta.formats)}."


def _more_items(page: Page, output_format: Format) -> Diagnostic | None:
    # Only json carries total and next_cursor in its envelope; jsonl and table would hide them.
    # With --limit 0 nothing is printed, so the notice is the only place the total appears.
    count_only = not page.items and page.total > 0
    if output_format is Format.JSON or (page.next_cursor is None and not count_only):
        return None
    return Diagnostic.of(
        MORE_ITEMS,
        f"{len(page.items)} of {page.total} items printed.",
        hint=(
            "Pass --limit above 0 to print items."
            if page.next_cursor is None
            else "Pass --cursor with details.next_cursor for the next page."
        ),
        details={"total": page.total, "next_cursor": page.next_cursor},
    )


def _envelope(page: Page) -> dict[str, Any]:
    return {
        **page.header,
        "total": page.total,
        "items": page.items,
        "next_cursor": page.next_cursor,
    }
