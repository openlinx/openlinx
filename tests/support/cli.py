"""Run the CLI in tests: in process with Typer's `CliRunner` (design D8)."""

from dataclasses import dataclass

from typer.testing import CliRunner

from spider.cli.app import app


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


def run_cli(*args: str, input: str | bytes | None = None) -> CliResult:
    """Run `spider <args>` in process; stdout and stderr are the bytes exactly as written."""
    result = CliRunner().invoke(app, list(args), input=input)
    return CliResult(result.exit_code, result.stdout_bytes, result.stderr_bytes)
