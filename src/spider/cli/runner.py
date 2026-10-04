"""Runs the app; each failure is a diagnostic (design D5 of 010-add-workspace-and-cli-contract)."""

import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

import typer

# Typer 0.27 vendors Click and does not re-export its UsageError.
from typer._click.exceptions import MissingParameter
from typer._click.exceptions import UsageError as ClickUsageError
from typer.core import TyperGroup

from spider import APP_NAME
from spider.cli.meta import formats_hint, meta_of
from spider.cli.options import GLOBAL_FLAGS
from spider.clock import SystemClock
from spider.output.diagnostics import ExitCode, InternalError, SpiderError, UsageError
from spider.output.reporter import CliReporter, Reporter
from spider.output.writer import Document, Output, Rows
from spider.workspace.tables import SettingsTables


@dataclass(frozen=True)
class Invocation:
    output: Output
    reporter: Reporter
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
        args = list(sys.argv[1:] if args is None else args) or ["--help"]
        # The one place the process streams are read; spider.output only takes them.
        output = Output(sys.stdout.buffer, sys.stderr.buffer)  # noqa: TID251
        try:
            _check_global_flags_follow_the_command(args)
            returned = super().main(
                args,
                prog_name,
                complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                obj=Invocation(output, CliReporter(output, SystemClock()), self.settings_tables),
                **extra,
            )
            # A Command returns its result; --help and --version end in an Exit, whose code
            # returns. Rows are made while they are written, so their errors land here too.
            if isinstance(returned, Document):
                output.document(returned)
                if returned.notice is not None:
                    output.diagnostic(returned.notice)
                if returned.error is not None:
                    raise returned.error
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
        except Exception:
            internal = _internal_error()
            output.diagnostic(internal.diagnostic)
            sys.exit(internal.exit_code)
        sys.exit(returned)


def _check_global_flags_follow_the_command(args: Sequence[str]) -> None:
    # Click would only say "No such option", which does not tell an agent where the flag goes.
    for arg in args:
        if not arg.startswith("-") or arg == "--":
            return
        flag = arg.partition("=")[0]
        if flag in GLOBAL_FLAGS:
            raise UsageError(
                "usage_error",
                f"{flag} is given before the Command name.",
                hint=f"Put {flag} after the Command name, as in: {APP_NAME} init {flag} ...",
            )


def _internal_error() -> InternalError:
    return InternalError(
        "internal_error",
        f"An unexpected failure stopped the Command. This is a bug in {APP_NAME}.",
        hint="Report it with details.traceback.",
        details={"traceback": traceback.format_exc()},
    )


def _invalid_value(error: typer.BadParameter) -> UsageError:
    hint = None
    if error.param is not None and error.param.name == "output_format" and error.ctx is not None:
        callback = error.ctx.command.callback
        meta = meta_of(callback) if callback is not None else None
        hint = formats_hint(meta) if meta is not None else None
    return UsageError("invalid_value", error.format_message(), hint=hint)
