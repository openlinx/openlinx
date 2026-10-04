"""Help and version are plain text (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_help_of_a_command_is_plain_text_usage() -> None:
    result = run_cli("init", "--help")

    assert (result.exit_code, b"Usage:" in result.stdout) == (0, True)


def test_no_arguments_prints_the_root_help_and_exits_0() -> None:
    result = run_cli()

    assert (result.exit_code, result.stdout, result.stderr) == (0, run_cli("--help").stdout, b"")
