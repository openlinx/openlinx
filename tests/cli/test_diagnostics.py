"""Diagnostics on stderr and exit codes (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_unknown_command_is_a_usage_error() -> None:
    result = run_cli("nosuchcommand")

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "usage_error")


def test_error_object_has_exactly_the_diagnostic_keys() -> None:
    error = run_cli("nosuchcommand").stderr_json_lines()[-1]

    assert (set(error), error["level"]) == (
        {"level", "code", "message", "hint", "details"},
        "error",
    )


def test_nothing_on_stdout_when_a_command_fails() -> None:
    assert run_cli("nosuchcommand").stdout == b""
