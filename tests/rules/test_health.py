"""The Health Score's formula (040-add-rules D8; seam 4)."""

from spider.rules.health import health_score


def test_pages_with_issue_type_issues_lower_the_score() -> None:
    assert health_score(10, 3) == 70


def test_score_is_rounded_down() -> None:
    assert health_score(3, 1) == 66
