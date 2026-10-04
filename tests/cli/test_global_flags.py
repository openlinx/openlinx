"""Global flags (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_before_the_command_name() -> None:
    result = run_cli("--format", "table", "init")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], "after the Command name" in (error["hint"] or "")) == (
        2,
        "usage_error",
        True,
    )
