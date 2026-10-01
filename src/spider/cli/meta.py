"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
from collections.abc import Callable, Sequence
from typing import Any, cast

from spider.output.diagnostics import UsageError
from spider.output.writer import Document, Format


def command_meta[**P](
    *, formats: Sequence[Format]
) -> Callable[[Callable[P, Any]], Callable[P, Document]]:
    def decorate(command: Callable[P, Any]) -> Callable[P, Document]:
        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> Document:
            output_format = cast(Format, kwargs["output_format"])
            if output_format not in formats:
                raise UsageError(
                    "invalid_value",
                    f"This Command has no {output_format} format.",
                    hint=f"Use --format with one of: {', '.join(formats)}.",
                )
            return Document(command(*args, **kwargs), output_format)

        return run

    return decorate
