"""`@command_meta`: what a Command outputs (design D7 of 010-add-workspace-and-cli-contract)."""

import functools
from collections.abc import Callable
from typing import Any, Literal

from spider.output.writer import Output


def command_meta[**P](
    *, output: Literal["document"]
) -> Callable[[Callable[P, Any]], Callable[P, None]]:
    def decorate(command: Callable[P, Any]) -> Callable[P, None]:
        @functools.wraps(command)
        def run(*args: P.args, **kwargs: P.kwargs) -> None:
            Output().document(command(*args, **kwargs))

        return run

    return decorate
