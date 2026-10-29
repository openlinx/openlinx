"""Progress event lines (design D3 of 010-add-workspace-and-cli-contract, cli-contract)."""

from datetime import UTC, datetime

from openlinx.output.events import event_line
from tests.support.clock import FakeClock


def test_event_line() -> None:
    clock = FakeClock()
    target = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)
    clock.advance((target - clock.now()).total_seconds())

    line = event_line("progress", {"crawled": 3}, clock.now())

    assert line == (b'{"event":"progress","ts":"2026-09-27T14:03:12.345Z","data":{"crawled":3}}\n')
