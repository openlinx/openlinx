"""`spider commands` (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_the_command_lists_itself() -> None:
    names = [entry["name"] for entry in run_cli("commands").json()["commands"]]

    assert "commands" in names
