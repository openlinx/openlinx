"""Rows Commands (010-add-workspace-and-cli-contract, cli-contract)."""

import subprocess
import sys
import threading
from pathlib import Path

from tests.support.app import example_app
from tests.support.cli import run_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_WAITING_ROWS = (
    "import sys; from tests.support.app import example_app; "
    "example_app()(['example-rows-waiting', sys.argv[1]])"
)


def test_rows_by_default() -> None:
    assert run_cli("example-rows", app=example_app()).stdout == b'{"n":1}\n{"n":2}\n'


def test_each_row_is_flushed_before_the_next_one_is_made(tmp_path: Path) -> None:
    signal = tmp_path / "signal"
    process = subprocess.Popen(
        [sys.executable, "-c", RUN_WAITING_ROWS, str(signal)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
    )
    # A row held back until the end would never arrive: the Command waits for the signal.
    watchdog = threading.Timer(20, process.kill)
    watchdog.start()
    assert process.stdout is not None
    first = process.stdout.readline()
    signal.touch()
    rest, _ = process.communicate(timeout=20)
    watchdog.cancel()

    assert (first, rest) == (b'{"n":1}\n', b'{"n":2}\n')
