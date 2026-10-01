"""List Commands (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_compact_document() -> None:
    result = run_cli("example-list", "--limit", "5", app=example_app())

    assert result.stdout == (
        b'{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}\n'
    )


def test_items_as_lines() -> None:
    result = run_cli("example-list", "--format", "jsonl", "--limit", "2", app=example_app())

    assert result.stdout == b'{"n":1}\n{"n":2}\n'


def test_a_list_table_shows_items_not_the_envelope() -> None:
    stdout = run_cli("example-list", "--format", "table", app=example_app()).stdout

    assert (b"next_cursor" in stdout, b"items" in stdout) == (False, False)
