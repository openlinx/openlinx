"""Runs the app; each failure is a diagnostic (design D5 of 010-add-workspace-and-cli-contract)."""

import sys
from collections.abc import Sequence
from typing import Any, NoReturn

# Typer 0.27 vendors Click and does not re-export its UsageError.
from typer._click.exceptions import UsageError as ClickUsageError
from typer.core import TyperGroup

from spider.output.diagnostics import ExitCode, SpiderError, UsageError
from spider.output.writer import Document, Output


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
        output = Output()
        try:
            returned = super().main(
                args,
                prog_name,
                complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                obj=output,
                **extra,
            )
        except ClickUsageError as error:
            output.diagnostic(UsageError("usage_error", error.format_message()).diagnostic)
            sys.exit(ExitCode.USAGE)
        except SpiderError as error:
            output.diagnostic(error.diagnostic)
            sys.exit(error.exit_code)
        # A Command returns its Document; --help and --version end in an Exit, whose code returns.
        if isinstance(returned, Document):
            output.document(returned)
            sys.exit(ExitCode.OK)
        sys.exit(returned)
