"""Runs the app; each failure is a diagnostic (design D5 of 010-add-workspace-and-cli-contract)."""

import sys
from collections.abc import Sequence
from typing import Any, NoReturn

from typer._click.exceptions import UsageError as ClickUsageError
from typer.core import TyperGroup

from spider.output.diagnostics import SpiderError, UsageError
from spider.output.writer import Output


class SpiderGroup(TyperGroup):
    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> NoReturn:
        # Not no_args_is_help: from Click 8.2 on it raises a usage error, which exits 2.
        if not (sys.argv[1:] if args is None else args):
            args = ["--help"]
        try:
            exit_code = super().main(
                args,
                prog_name,
                complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except ClickUsageError as error:
            exit_code = _fail(UsageError("usage_error", error.format_message()))
        except SpiderError as error:
            exit_code = _fail(error)
        sys.exit(exit_code or 0)


def _fail(error: SpiderError) -> int:
    Output().error(error)
    return error.exit_code
