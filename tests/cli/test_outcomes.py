"""Partial results (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_the_result_of_a_failed_outcome_is_printed() -> None:
    assert run_cli("example-failed-outcome", app=example_app()).stdout == b'{"state":"failed"}\n'


def test_one_error_and_its_exit_code() -> None:
    result = run_cli("example-failed-outcome", app=example_app())
    levels = [line["level"] for line in result.stderr_json_lines()]

    assert (result.exit_code, levels.count("error"), levels[-1]) == (1, 1, "error")
