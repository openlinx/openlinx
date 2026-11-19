"""Verify allowed and refused Crawl State transitions."""

from itertools import product
from typing import get_args

from openlinx.store.records import CrawlState, StopReason
from openlinx.store.transitions import CrawlStateError, check_transition

STATES: tuple[CrawlState, ...] = get_args(CrawlState.__value__)
REASONS: tuple[StopReason | None, ...] = (None, *get_args(StopReason.__value__))


def _allowed(current: CrawlState, target: CrawlState, reason: StopReason | None) -> bool:
    try:
        check_transition(current, target, reason)
    except CrawlStateError:
        return False
    return True


def test_only_the_listed_transitions_are_allowed() -> None:
    allowed = {
        (current, target, reason)
        for current, target, reason in product(STATES, STATES, REASONS)
        if _allowed(current, target, reason)
    }

    assert allowed == {
        ("running", "completed", None),
        ("running", "stopped", "max_urls"),
        ("running", "stopped", "interrupt"),
        ("running", "stopped", "requested"),
        ("running", "failed", "seed_unreachable"),
        ("running", "failed", "site_unreachable"),
        ("running", "failed", "write_failed"),
        ("stopped", "running", None),
        ("failed", "running", None),
    }


def test_an_early_end_needs_a_reason_of_its_kind() -> None:
    assert [_allowed("running", "stopped", reason) for reason in (None, "seed_unreachable")] == [
        False,
        False,
    ]
