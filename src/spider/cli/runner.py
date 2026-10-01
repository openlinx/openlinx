"""Runs the app; each failure is a diagnostic (design D5 of 010-add-workspace-and-cli-contract)."""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

import typer

# Typer 0.27 vendors Click and does not re-export its UsageError.
from typer._click.exceptions import MissingParameter
from typer._click.exceptions import UsageError as ClickUsageError
from typer.core import TyperGroup

from spider.cli.meta import formats_hint, meta_of
from spider.output.diagnostics import ExitCode, SpiderError, UsageError
from spider.output.writer import Document, Output, Rows
from spider.workspace.tables import SettingsTables


@dataclass(frozen=True)
class Invocation:
    output: Output
    settings_tables: SettingsTables


class SpiderGroup(TyperGroup):
    # Set by build_app on a subclass per app, so tests never share a registry.
    settings_tables: SettingsTables

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
                obj=Invocation(output, self.settings_tables),
                **extra,
            )
            # A Command returns its result; --help and --version end in an Exit, whose code
            # returns. Rows are made while they are written, so their errors land here too.
            if isinstance(returned, Document):
                output.document(returned)
                returned = ExitCode.OK
            elif isinstance(returned, Rows):
                output.rows(returned)
                returned = ExitCode.OK
        except MissingParameter as error:
            # A BadParameter subclass, but a missing argument is a usage error (cli-contract).
            output.diagnostic(UsageError("usage_error", error.format_message()).diagnostic)
            sys.exit(ExitCode.USAGE)
        except typer.BadParameter as error:
            output.diagnostic(_invalid_value(error).diagnostic)
            sys.exit(ExitCode.USAGE)
        except ClickUsageError as error:
            output.diagnostic(UsageError("usage_error", error.format_message()).diagnostic)
            sys.exit(ExitCode.USAGE)
        except SpiderError as error:
            output.diagnostic(error.diagnostic)
            sys.exit(error.exit_code)
        sys.exit(returned)


def _invalid_value(error: typer.BadParameter) -> UsageError:
    hint = None
    if error.param is not None and error.param.name == "output_format" and error.ctx is not None:
        callback = error.ctx.command.callback
        meta = meta_of(callback) if callback is not None else None
        hint = formats_hint(meta) if meta is not None else None
    return UsageError("invalid_value", error.format_message(), hint=hint)
