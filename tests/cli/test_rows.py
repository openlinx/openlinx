"""Rows Commands (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import PROCESS_TIMEOUT, run_cli, start_example_process


def test_rows_by_default() -> None:
    assert run_cli("example-rows", app=example_app()).stdout == b'{"n":1}\n{"n":2}\n'


def test_each_row_is_flushed_before_the_next_one_is_made() -> None:
    # A row held back until the end would never arrive: the Command waits for the go-line.
    process = start_example_process("example-rows-waiting")
    assert process.stdout is not None
    first = process.stdout.readline()
    rest, _ = process.communicate(b"go\n", timeout=PROCESS_TIMEOUT)

    assert (first, rest) == (b'{"n":1}\n', b'{"n":2}\n')
