"""Global flags (010-add-workspace-and-cli-contract, cli-contract)."""

from pathlib import Path

from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


def test_before_the_command_name() -> None:
    result = run_cli("--format", "table", "init")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], "after the Command name" in (error["hint"] or "")) == (
        2,
        "usage_error",
        True,
    )


def test_after_the_command_name(shop: Path) -> None:
    assert run_cli("init", "--format", "json").exit_code == 0


def test_a_flag_the_command_does_not_use(temp_workspace: TempWorkspace) -> None:
    result = run_cli("commands", "--workspace", str(temp_workspace.root))

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "usage_error")
