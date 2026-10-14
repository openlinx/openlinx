"""`spider issues` (050-add-query-and-segments, querying; seam 1)."""

from tests.support.cli import run_cli
from tests.support.crawl_store import (
    UNDER_A,
    UNDER_B,
    UNDER_C,
    UNDER_D,
    crawl_store,
    later_rule,
    under,
)
from tests.support.workspace import TempWorkspace

# A (warning, high), B (issue, low), C (issue, high) and D (opportunity, high).
FILTERED_ISSUES = (
    later_rule("rule-a", "warning", "high", UNDER_A),
    later_rule("rule-b", "issue", "low", UNDER_B),
    later_rule("rule-c", "issue", "high", UNDER_C),
    later_rule("rule-d", "opportunity", "high", UNDER_D),
)
ONE_UNDER_EACH = (*under("a", 1), *under("b", 1), *under("c", 1), *under("d", 1))


def test_filters_combine(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, links=ONE_UNDER_EACH, later_rules=FILTERED_ISSUES, completed=True)

    result = run_cli("issues", "--type", "issue,warning", "--priority", "high")

    assert [item["rule_id"] for item in result.json()["items"]] == ["rule-c", "rule-a"]


def test_filter_values_are_repeatable_and_case_insensitive(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, links=ONE_UNDER_EACH, later_rules=FILTERED_ISSUES, completed=True)

    result = run_cli("issues", "--type", "ISSUE", "--type", "Warning", "--priority", "High")

    assert [item["rule_id"] for item in result.json()["items"]] == ["rule-c", "rule-a"]


def test_filter_by_category(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, pages={"https://example.com/a": {"title_count": 0, "h1_count": 0}})

    result = run_cli("issues", "--category", "headings")

    assert [item["rule_id"] for item in result.json()["items"]] == ["h1-missing"]
