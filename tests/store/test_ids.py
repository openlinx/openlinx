"""Crawl ids (015-add-crawl-store, crawl-store)."""

import re
import secrets
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from spider.store.ids import new_crawl_id
from tests.support.randomness import scripted_choice


def test_id_from_the_start_time() -> None:
    started_at = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)

    assert new_crawl_id(started_at, scripted_choice("k3f9")) == "20260927-140312-k3f9"


@given(
    # timezones= makes every drawn start time UTC.
    st.datetimes(
        min_value=datetime(2000, 1, 1),  # noqa: DTZ001 - hypothesis takes naive bounds
        max_value=datetime(2099, 12, 31, 23, 59, 59, 999000),  # noqa: DTZ001 - hypothesis takes naive bounds
        timezones=st.just(UTC),
    )
)
def test_character_set(started_at: datetime) -> None:
    crawl_id = new_crawl_id(started_at, secrets.choice)

    assert re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-hjkmnp-tv-z]{4}", crawl_id)
