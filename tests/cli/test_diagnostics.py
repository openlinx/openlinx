"""Diagnostics on stderr and exit codes (010-add-workspace-and-cli-contract, cli-contract)."""

import json

import pytest

from tests.support.app import example_app
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


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


def test_only_json_lines_on_stderr(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "notes.txt").write_bytes(b"")
    site = temp_workspace.root / "notes.txt" / "site"

    lines = run_cli("init", "--workspace", str(site)).stderr.splitlines()

    assert [type(json.loads(line)) for line in lines] == [dict]


def test_a_missing_argument_is_a_usage_error() -> None:
    result = run_cli("example-needs-argument", app=example_app())

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "usage_error")


def test_unexpected_failure() -> None:
    result = run_cli("example-raises", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        error["message"].endswith("This is a bug in OpenLinx."),
        "RuntimeError: disk exploded" in error["details"]["traceback"],
    ) == (70, "internal_error", True, True)


def test_a_warning_inside_a_result() -> None:
    result = run_cli("example-warning-inside", app=example_app())

    assert [set(entry) for entry in result.json()["warnings"]] == [
        {"level", "code", "message", "hint", "details"}
    ]


@pytest.mark.parametrize("command", ["example-interrupted", "example-aborted"])
def test_interrupted(command: str) -> None:
    result = run_cli(command, app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["level"], error["code"]) == (130, "error", "interrupted")


def test_interrupted_rows_keep_the_rows_already_written() -> None:
    result = run_cli("example-rows-interrupted", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, result.stdout, error["code"]) == (130, b'{"n":1}\n', "interrupted")
