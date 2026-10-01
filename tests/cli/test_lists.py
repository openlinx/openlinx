"""List Commands (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_compact_document() -> None:
    result = run_cli("example-list", "--limit", "5", app=example_app())

    assert result.stdout == (
        b'{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}\n'
    )
