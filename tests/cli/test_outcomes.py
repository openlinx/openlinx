"""Partial results (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_the_result_of_a_failed_outcome_is_printed() -> None:
    assert run_cli("example-failed-outcome", app=example_app()).stdout == b'{"state":"failed"}\n'
