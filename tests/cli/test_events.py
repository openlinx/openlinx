"""Progress events (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_the_result_goes_to_stdout() -> None:
    assert run_cli("example-progress", app=example_app()).stdout == b'{"urls":10}\n'


def test_events_go_to_stderr() -> None:
    lines = run_cli("example-progress", app=example_app()).stderr_json_lines()

    assert [line["event"] for line in lines] == ["progress", "progress"]
