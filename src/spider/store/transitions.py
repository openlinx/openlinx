"""Crawl State transitions: one table and one check (020-add-crawl-core D12)."""

from collections.abc import Mapping

from spider.store.records import CrawlState, StopReason

# Each allowed change of state, with the stop reasons it allows; 060 adds interrupted.
TRANSITIONS: Mapping[tuple[CrawlState, CrawlState], frozenset[StopReason | None]] = {
    ("running", "completed"): frozenset({None}),
    ("running", "stopped"): frozenset({"max_urls", "interrupt", "requested"}),
    ("running", "failed"): frozenset({"seed_unreachable", "site_unreachable", "write_failed"}),
    ("stopped", "running"): frozenset({None}),
    ("failed", "running"): frozenset({None}),
}


class CrawlStateError(RuntimeError):
    """A change of Crawl State the table does not allow: a bug in its caller."""


def check_transition(
    current: CrawlState, target: CrawlState, stop_reason: StopReason | None
) -> None:
    reasons = TRANSITIONS.get((current, target))
    if reasons is None:
        raise CrawlStateError(f"A Crawl cannot go from {current} to {target}.")
    if stop_reason not in reasons:
        raise CrawlStateError(
            f"A Crawl cannot go from {current} to {target} with the stop reason {stop_reason}."
        )
