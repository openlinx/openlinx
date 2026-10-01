"""Help and version are plain text (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_help_of_a_command_is_plain_text_usage() -> None:
    result = run_cli("commands", "--help")

    assert (result.exit_code, b"Usage:" in result.stdout) == (0, True)
