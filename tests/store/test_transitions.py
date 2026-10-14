"""Crawl State transitions (020-add-crawl-core D12; seam 4)."""

from itertools import product
from typing import get_args

from spider.store.records import CrawlState, StopReason
from spider.store.transitions import CrawlStateError, check_transition

STATES: tuple[CrawlState, ...] = get_args(CrawlState.__value__)
REASONS: tuple[StopReason | None, ...] = (None, *get_args(StopReason.__value__))


def _allowed(current: CrawlState, target: CrawlState, reason: StopReason | None) -> bool:
    try:
        check_transition(current, target, reason)
    except CrawlStateError:
        return False
    return True


def test_only_the_listed_transitions_are_allowed() -> None:
    allowed = [
        (current, target)
        for current, target in product(STATES, STATES)
        if any(_allowed(current, target, reason) for reason in REASONS)
    ]

    assert sorted(allowed) == sorted(
        [
            ("running", "completed"),
            ("running", "stopped"),
            ("running", "failed"),
            ("stopped", "running"),
            ("failed", "running"),
        ]
    )


def test_an_early_end_needs_a_reason_of_its_kind() -> None:
    assert [_allowed("running", "stopped", reason) for reason in (None, "seed_unreachable")] == [
        False,
        False,
    ]
