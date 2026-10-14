"""The Issues of the Query Service (050-add-query-and-segments, querying; seam 2)."""

from pathlib import Path

import pytest

from spider.output.diagnostics import SpiderError
from spider.rules.titles import TITLE_MISSING, TITLE_TOO_LONG
from spider.services.query import QueryRequest, issue_detail, issue_filters, issue_list
from spider.store.records import LATEST
from tests.support.crawl_store import (
    UNDER_A,
    UNDER_B,
    UNDER_C,
    UNDER_D,
    crawl_store,
    later_rule,
    under,
)
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def request(temp_workspace: TempWorkspace) -> QueryRequest:
    return QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, workspace=None, crawl=LATEST
    )


ISSUES_A_TO_D = (
    later_rule("rule-a", "warning", "high", UNDER_A),
    later_rule("rule-b", "issue", "low", UNDER_B),
    later_rule("rule-c", "issue", "high", UNDER_C),
    later_rule("rule-d", "issue", "high", UNDER_D),
)


def test_order(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace,
        links=(*under("a", 50), *under("b", 3), *under("c", 1), *under("d", 9)),
        later_rules=ISSUES_A_TO_D,
        completed=True,
    )

    found = issue_list(request(temp_workspace)).items

    assert [item["rule_id"] for item in found] == ["rule-d", "rule-c", "rule-b", "rule-a"]


def test_item_fields(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace, pages={url: {"title_count": 0} for url in under("p", 4)}, completed=True
    )

    found = issue_list(request(temp_workspace)).items

    # The description that spider rules show title-missing prints.
    assert found == [
        {
            "rule_id": "title-missing",
            "category": "titles",
            "issue_type": "issue",
            "priority": "high",
            "affected_count": 4,
            "description": TITLE_MISSING.description,
        }
    ]


def test_issues_of_a_running_crawl_are_computed_live(temp_workspace: TempWorkspace) -> None:
    crawl_file = crawl_store(temp_workspace, pages={"https://example.com/a": {"title_count": 0}})

    found = issue_list(request(temp_workspace)).items

    assert (
        query(crawl_file, "SELECT state FROM crawl"),
        query(crawl_file, "SELECT count(*) FROM affected_urls"),
        [(item["rule_id"], item["affected_count"]) for item in found],
    ) == ([("running",)], [(0,)], [("title-missing", 1)])


def test_a_rule_that_did_not_fire(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, completed=True)

    found = issue_detail(request(temp_workspace), "h1-missing")

    assert (found.total, found.items) == (0, [])


def test_thresholds_recorded_for_the_crawl(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, rules={"title-too-long": {"max_chars": 70}}, completed=True)

    found = issue_detail(request(temp_workspace), "title-too-long")

    assert found.header["rule"]["thresholds"] == {"max_chars": 70}


def test_guidance_of_the_rule(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, completed=True)

    found = issue_detail(request(temp_workspace), "title-too-long")

    # The how_to_fix that spider rules show title-too-long prints.
    assert found.header["rule"]["how_to_fix"] == TITLE_TOO_LONG.how_to_fix


def test_the_reproducing_query_of_the_rule(temp_workspace: TempWorkspace) -> None:
    crawl_file = crawl_store(temp_workspace, completed=True)

    found = issue_detail(request(temp_workspace), "title-missing")

    assert [(found.header["rule"]["reproduce_sql"],)] == query(
        crawl_file, "SELECT reproduce_sql FROM rules WHERE id = 'title-missing'"
    )


def test_detail_of_an_affected_url(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, statuses={"https://example.com/gone": 404}, completed=True)

    found = issue_detail(request(temp_workspace), "internal-4xx")

    assert found.items == [{"url": "https://example.com/gone", "detail": {"status_code": 404}}]


# Recorded out of url order, so the order of insertion is not the order of url.
GONE = ["https://example.com/gone/z", "https://example.com/gone/a", "https://example.com/gone/m"]


def test_affected_urls_are_paged_in_url_order(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, statuses=dict.fromkeys(GONE, 404), completed=True)

    first = issue_detail(request(temp_workspace), "internal-4xx", limit=2)
    second = issue_detail(
        request(temp_workspace), "internal-4xx", limit=2, cursor=first.next_cursor
    )

    assert (
        [item["url"] for item in first.items],
        [item["url"] for item in second.items],
        (first.total, second.total, second.next_cursor),
    ) == (
        ["https://example.com/gone/a", "https://example.com/gone/m"],
        ["https://example.com/gone/z"],
        (3, 3, None),
    )


def test_a_cursor_of_another_rule_is_refused(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, statuses=dict.fromkeys(GONE, 404), completed=True)
    first = issue_detail(request(temp_workspace), "internal-4xx", limit=2)

    with pytest.raises(SpiderError) as raised:
        issue_detail(request(temp_workspace), "internal-5xx", limit=2, cursor=first.next_cursor)

    assert raised.value.code == "invalid_cursor"


def test_an_empty_filter_value_is_refused() -> None:
    with pytest.raises(SpiderError) as raised:
        issue_filters(issue_types=["issue,,warning"])

    assert (raised.value.code, raised.value.diagnostic.message) == (
        "invalid_value",
        "--type 'issue,,warning' has an empty value.",
    )


def test_the_first_unknown_value_given_is_named() -> None:
    with pytest.raises(SpiderError) as raised:
        issue_filters(priorities=["urgent", "asap"])

    assert raised.value.diagnostic.details["value"] == "urgent"


def test_issue_types_then_priorities_are_ordered_as_declared(
    temp_workspace: TempWorkspace,
) -> None:
    # Each fires once, so only the Issue Type and the Priority order them; alphabetical
    # order would give issue/low, issue/medium, opportunity, warning.
    crawl_store(
        temp_workspace,
        links=(*under("a", 1), *under("b", 1), *under("c", 1), *under("d", 1)),
        later_rules=(
            later_rule("rule-a", "opportunity", "high", UNDER_A),
            later_rule("rule-b", "warning", "high", UNDER_B),
            later_rule("rule-c", "issue", "low", UNDER_C),
            later_rule("rule-d", "issue", "medium", UNDER_D),
        ),
        completed=True,
    )

    found = issue_list(request(temp_workspace)).items

    assert [item["rule_id"] for item in found] == ["rule-d", "rule-c", "rule-b", "rule-a"]


TWO_ISSUES = (
    later_rule("rule-a", "issue", "high", UNDER_A),
    later_rule("rule-b", "warning", "high", UNDER_B),
)


def at(temp_workspace: TempWorkspace, crawl_file: Path) -> QueryRequest:
    return QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, workspace=None, crawl=str(crawl_file)
    )


def test_a_cursor_of_the_issue_list_of_another_crawl_is_refused(
    temp_workspace: TempWorkspace,
) -> None:
    links = (*under("a", 1), *under("b", 1))
    first = crawl_store(temp_workspace, links=links, later_rules=TWO_ISSUES, completed=True)
    second = crawl_store(temp_workspace, links=links, later_rules=TWO_ISSUES, completed=True)
    page = issue_list(at(temp_workspace, first), limit=1)

    with pytest.raises(SpiderError) as raised:
        issue_list(at(temp_workspace, second), limit=1, cursor=page.next_cursor)

    assert raised.value.code == "invalid_cursor"


def test_a_cursor_of_the_issue_list_with_other_filters_is_refused(
    temp_workspace: TempWorkspace,
) -> None:
    links = (*under("a", 1), *under("b", 1))
    crawl_store(temp_workspace, links=links, later_rules=TWO_ISSUES, completed=True)
    page = issue_list(request(temp_workspace), limit=1)

    with pytest.raises(SpiderError) as raised:
        issue_list(
            request(temp_workspace),
            issue_filters(priorities=["high"]),
            limit=1,
            cursor=page.next_cursor,
        )

    assert raised.value.code == "invalid_cursor"


def test_a_cursor_of_the_affected_urls_of_another_crawl_is_refused(
    temp_workspace: TempWorkspace,
) -> None:
    first = crawl_store(temp_workspace, statuses=dict.fromkeys(GONE, 404), completed=True)
    second = crawl_store(temp_workspace, statuses=dict.fromkeys(GONE, 404), completed=True)
    page = issue_detail(at(temp_workspace, first), "internal-4xx", limit=1)

    with pytest.raises(SpiderError) as raised:
        issue_detail(at(temp_workspace, second), "internal-4xx", limit=1, cursor=page.next_cursor)

    assert raised.value.code == "invalid_cursor"


def test_the_rule_of_an_issue_is_the_one_the_crawl_recorded(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_store(temp_workspace, links=under("a", 1), later_rules=TWO_ISSUES[:1], completed=True)

    found = issue_detail(request(temp_workspace), "rule-a")

    assert found.header["rule"] == {
        "rule_id": "rule-a",
        "category": "titles",
        "issue_type": "issue",
        "priority": "high",
        "description": "What rule-a checks.",
        "why_it_matters": "Why rule-a matters.",
        "how_to_fix": "How to fix rule-a.",
        "thresholds": {},
        "reproduce_sql": UNDER_A,
    }


def test_an_issue_is_described_as_the_crawl_recorded_its_rule(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_store(temp_workspace, links=under("a", 1), later_rules=TWO_ISSUES[:1], completed=True)

    found = issue_list(request(temp_workspace)).items

    assert [item["description"] for item in found] == ["What rule-a checks."]


def test_fields_are_checked_before_the_crawl_is_read(temp_workspace: TempWorkspace) -> None:
    missing = at(temp_workspace, temp_workspace.root / "missing.sqlite")

    with pytest.raises(SpiderError) as raised:
        issue_list(missing, fields="bogus")

    assert raised.value.code == "unknown_field"
