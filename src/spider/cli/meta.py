"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from spider.output.diagnostics import UsageError
from spider.output.writer import Document, Format

type OutputKind = Literal["document", "list"]


@dataclass(frozen=True)
class Fields:
    available: tuple[str, ...]
    default: tuple[str, ...]


# The parameters the wrapper reads, by output kind; each Command declares them itself.
REQUIRED_PARAMETERS: Mapping[OutputKind, tuple[str, ...]] = {
    "document": ("output_format",),
    "list": ("output_format", "limit"),
}


def command_meta[**P](
    *, output: OutputKind, formats: Sequence[Format], fields: Fields | None = None
) -> Callable[[Callable[P, Any]], Callable[P, Document]]:
    def decorate(command: Callable[P, Any]) -> Callable[P, Document]:
        declared = inspect.signature(command).parameters
        missing = [name for name in REQUIRED_PARAMETERS[output] if name not in declared]
        if missing or (output == "list") != (fields is not None):
            raise TypeError(
                f"Command {command.__name__}: a {output} Command needs the parameters "
                f"{', '.join(REQUIRED_PARAMETERS[output])}, and fields only if it is a list."
            )

        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> Document:
            output_format = cast(Format, kwargs["output_format"])
            if output_format not in formats:
                raise UsageError(
                    "invalid_value",
                    f"This Command has no {output_format} format.",
                    hint=f"Use --format with one of: {', '.join(formats)}.",
                )
            result = command(*args, **kwargs)
            if fields is not None:
                result = _envelope(result, fields, cast(int, kwargs["limit"]))
            return Document(result, output_format)

        return run

    return decorate


def _envelope(items: Sequence[Mapping[str, Any]], fields: Fields, limit: int) -> dict[str, Any]:
    page = [{name: item[name] for name in fields.default} for item in items[:limit]]
    return {"total": len(items), "items": page, "next_cursor": None}
