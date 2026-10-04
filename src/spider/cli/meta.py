"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
import inspect
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from spider.output.diagnostics import Diagnostic, UsageError
from spider.output.paging import Fields, Page
from spider.output.writer import Document, Format, Rows

type OutputKind = Literal["document", "list", "rows"]


@dataclass(frozen=True)
class CommandMeta:
    output: OutputKind
    formats: tuple[Format, ...]
    fields: Fields | None


# What each output kind can serve, and the parameters its wrapper reads from the Command.
KIND_FORMATS: Mapping[OutputKind, frozenset[Format]] = {
    "document": frozenset({Format.JSON, Format.TABLE}),
    "list": frozenset({Format.JSON, Format.JSONL, Format.TABLE}),
    "rows": frozenset({Format.JSONL}),
}
KIND_PARAMETERS: Mapping[OutputKind, tuple[str, ...]] = {
    "document": ("output_format",),
    "list": ("output_format", "limit"),
    "rows": ("output_format",),
}


def command_meta[**P](
    *, output: OutputKind, formats: Sequence[Format], fields: Fields | None = None
) -> Callable[[Callable[P, Any]], Callable[P, Document | Rows]]:
    meta = CommandMeta(output, tuple(formats), fields)

    def decorate(command: Callable[P, Any]) -> Callable[P, Document | Rows]:
        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> Document | Rows:
            output_format = cast(Format, kwargs["output_format"])
            if output_format not in meta.formats:
                raise UsageError(
                    "invalid_value",
                    f"This Command has no {output_format} format.",
                    hint=formats_hint(meta),
                )
            result = command(*args, **kwargs)
            if meta.fields is None:
                return Document(result, output_format, "document")
            if meta.output == "rows":
                return Rows(_project_all(result, meta.fields), output_format)
            return Document(
                _envelope(result), output_format, "list", _more_items(result, output_format)
            )

        run.command_meta = meta  # type: ignore[attr-defined]
        return run

    return decorate


def meta_of(command: Callable[..., Any]) -> CommandMeta | None:
    meta: CommandMeta | None = getattr(command, "command_meta", None)
    return meta


def check_command(command: Callable[..., Any]) -> None:
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
    if "output_format" in declared and (declared["output_format"].default,) != meta.formats[:1]:
        problems.append("its --format default is not the first of its formats")
    if (meta.output == "document") != (meta.fields is None):
        problems.append("fields belong to list and rows Commands only")
    elif meta.fields is not None and not set(meta.fields.default) <= set(meta.fields.available):
        problems.append("its default fields are not all available")
    if problems:
        raise TypeError(f"Command {command.__name__}: {'; '.join(problems)}.")


def formats_hint(meta: CommandMeta) -> str:
    return f"Use --format with one of: {', '.join(meta.formats)}."


def _project(item: Mapping[str, Any], fields: Fields) -> dict[str, Any]:
    return {name: item[name] for name in fields.default}


def _project_all(rows: Iterable[Mapping[str, Any]], fields: Fields) -> Iterator[dict[str, Any]]:
    for row in rows:
        yield _project(row, fields)


def _more_items(page: Page, output_format: Format) -> Diagnostic | None:
    # Only json carries next_cursor in its envelope; jsonl and table would hide the next page.
    if output_format is Format.JSON or page.next_cursor is None:
        return None
    return Diagnostic(
        "info",
        "more_items",
        f"{len(page.items)} of {page.total} items printed.",
        hint="Pass --cursor with details.next_cursor for the next page.",
        details={"total": page.total, "next_cursor": page.next_cursor},
    )


def _envelope(page: Page) -> dict[str, Any]:
    return {"total": page.total, "items": page.items, "next_cursor": page.next_cursor}
