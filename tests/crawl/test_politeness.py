"""Politeness limits (020-add-crawl-core D7; seam 4)."""

import pytest

from spider.crawl.politeness import global_cap


@pytest.mark.parametrize(("concurrency", "cap"), [(1, 20), (5, 20), (6, 24), (25, 100), (50, 100)])
def test_the_global_cap_is_four_times_the_concurrency_within_20_to_100(
    concurrency: int, cap: int
) -> None:
    assert global_cap(concurrency) == cap
