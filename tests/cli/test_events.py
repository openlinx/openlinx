"""Progress events (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_the_result_goes_to_stdout() -> None:
    assert run_cli("example-progress", app=example_app()).stdout == b'{"urls":10}\n'
