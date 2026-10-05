"""Crawl ids (015-add-crawl-store, crawl-store)."""

from datetime import UTC, datetime

from spider.store.ids import new_crawl_id
from tests.support.randomness import scripted_choice


def test_id_from_the_start_time() -> None:
    started_at = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)

    assert new_crawl_id(started_at, scripted_choice("k3f9")) == "20260927-140312-k3f9"
