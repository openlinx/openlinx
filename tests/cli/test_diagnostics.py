"""Diagnostics on stderr and exit codes (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_unknown_command_is_a_usage_error() -> None:
    result = run_cli("nosuchcommand")

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "usage_error")
