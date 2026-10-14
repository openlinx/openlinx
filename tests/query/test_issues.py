"""The Issues of the Query Service (050-add-query-and-segments, querying; seam 2)."""

from spider.rules.titles import TITLE_MISSING
from spider.services.query import QueryRequest, issue_list
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
