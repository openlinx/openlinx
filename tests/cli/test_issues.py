"""`spider issues` and `spider issue` (050-add-query-and-segments, querying; seam 1, and 3 with real
processes)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.cli import run_cli, run_cli_process
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


def test_unknown_issue_type(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace)

    result = run_cli("issues", "--type", "critical")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["details"]["accepted"]) == (
        2,
        "invalid_value",
        ["issue", "warning", "opportunity"],
    )


def test_a_rule_id_given_to_the_issue_list_is_a_usage_error(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_store(temp_workspace)

    result = run_cli("issues", "title-missing")

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "usage_error")


def test_unknown_rule_id(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace)

    result = run_cli("issue", "title-mising")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["details"]["suggestions"][0]) == (
        4,
        "rule_not_found",
        "title-missing",
    )


def test_the_affected_urls_of_an_issue_take_fields(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, statuses={"https://example.com/gone": 404}, completed=True)

    result = run_cli("issue", "internal-4xx", "--fields", "url")

    assert result.json()["items"] == [{"url": "https://example.com/gone"}]


E2E_PAGES = Site(
    {
        "/e2e/": Page(
            body='<title>Home</title><h1>Home</h1><a href="/e2e/notitle">No title</a> '
            '<a href="/e2e/gone">Gone</a>'
        ),
        "/e2e/notitle": Page(body="<h1>No title here</h1>"),
        "/e2e/gone": Status(404, body="Gone", content_type="text/plain"),
    }
)


@pytest.mark.slow
def test_issues_of_a_fixture_crawl_on_every_os(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(E2E_PAGES)
    crawl = run_cli_process("crawl", server.url("/e2e/"))

    result = run_cli_process("issues")
    detail = run_cli_process("issue", "internal-4xx")
    found = {item["rule_id"]: item["affected_count"] for item in result.json()["items"]}

    assert (
        crawl.exit_code,
        {rule_id: found.get(rule_id) for rule_id in ("internal-4xx", "title-missing")},
        detail.json()["items"],
    ) == (
        0,
        {"internal-4xx": 1, "title-missing": 1},
        [{"url": server.url("/e2e/gone"), "detail": {"status_code": 404}}],
    )
