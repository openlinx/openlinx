"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
from collections.abc import Callable, Sequence
from typing import Any, Literal

from spider.output.diagnostics import UsageError
from spider.output.writer import Format, Output


def command_meta[**P](
    *, output: Literal["document"], formats: Sequence[Format]
) -> Callable[[Callable[P, Any]], Callable[P, None]]:
    def decorate(command: Callable[P, Any]) -> Callable[P, None]:
        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> None:
            output_format = kwargs["output_format"]
            if output_format not in formats:
                raise UsageError(
                    "invalid_value",
                    f"This Command has no {output_format} format.",
                    hint=f"Use --format with one of: {', '.join(formats)}.",
                )
            Output().document(command(*args, **kwargs))

        return run

    return decorate
