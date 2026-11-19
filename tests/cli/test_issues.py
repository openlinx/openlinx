"""Exercise list filters, paging and discovery through the public Issues Command."""

from pathlib import Path

import pytest

from tests.support.cli import run_cli
from tests.support.crawl_store import IssueExample, crawl_store
from tests.support.crawls import create_crawl_at
from tests.support.workspace import TempWorkspace

_FILTER_EXAMPLES: tuple[IssueExample, ...] = (
    ("rule-a", "warning", "high", 1),
    ("rule-b", "issue", "low", 1),
    ("rule-c", "issue", "high", 1),
    ("rule-d", "opportunity", "high", 1),
)


@pytest.fixture
def issue_crawl(temp_workspace: TempWorkspace) -> Path:
    initialized = run_cli("init", "--workspace", str(temp_workspace.root))
    assert initialized.exit_code == 0, initialized.stderr
    return crawl_store(temp_workspace, example_issues=_FILTER_EXAMPLES)


@pytest.mark.parametrize(
    "filters",
    [
        pytest.param(("--type", "issue,warning", "--priority", "high"), id="comma-separated"),
        pytest.param(
            ("--type", " Warning,warning", "--type", " ISSUE ", "--priority", "HIGH"),
            id="repeatable-case-insensitive",
        ),
    ],
)
def test_filters_combine(
    temp_workspace: TempWorkspace, issue_crawl: Path, filters: tuple[str, ...]
) -> None:
    result = run_cli("issues", "--workspace", str(temp_workspace.root), *filters)

    assert result.exit_code == 0, result.stderr
    page = result.json()
    assert (page["total"], [item["rule_id"] for item in page["items"]], page["next_cursor"]) == (
        2,
        ["rule-c", "rule-a"],
        None,
    )


def test_priority_values_can_be_repeated(temp_workspace: TempWorkspace, issue_crawl: Path) -> None:
    result = run_cli(
        "issues",
        "--workspace",
        str(temp_workspace.root),
        "--type",
        "issue,warning",
        "--priority",
        "HiGh",
        "--priority",
        " LOW, medium ",
    )

    assert result.exit_code == 0, result.stderr
    assert [item["rule_id"] for item in result.json()["items"]] == ["rule-c", "rule-b", "rule-a"]


def test_equivalent_filters_keep_the_cursor(
    temp_workspace: TempWorkspace, issue_crawl: Path
) -> None:
    args = ("issues", "--workspace", str(temp_workspace.root), "--limit", "1")
    first = run_cli(*args, "--type", "ISSUE,warning", "--priority", "HIGH")

    assert first.exit_code == 0, first.stderr
    page = first.json()
    assert [item["rule_id"] for item in page["items"]] == ["rule-c"]
    cursor = page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    second = run_cli(
        *args,
        "--priority",
        "high,HIGH",
        "--type",
        "WARNING",
        "--type",
        "issue",
        "--cursor",
        cursor,
        "--fields",
        "rule_id",
    )

    assert second.exit_code == 0, second.stderr
    assert second.json() == {"total": 2, "items": [{"rule_id": "rule-a"}], "next_cursor": None}


@pytest.mark.parametrize("selection", ["type", "priority", "crawl"])
def test_a_cursor_rejects_another_selection(
    temp_workspace: TempWorkspace, issue_crawl: Path, selection: str
) -> None:
    args = ("issues", "--workspace", str(temp_workspace.root))
    first = run_cli(*args, "--type", "issue,warning", "--priority", "high", "--limit", "1")
    assert first.exit_code == 0, first.stderr
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    if selection == "crawl":
        create_crawl_at(temp_workspace, "2026-09-27T15:00:00.000Z", "next")
        original = run_cli(
            *args,
            "--crawl",
            str(issue_crawl),
            "--type",
            "issue,warning",
            "--priority",
            "high",
            "--cursor",
            cursor,
            "--fields",
            "rule_id",
        )
        assert original.exit_code == 0, original.stderr
        assert original.json()["items"] == [{"rule_id": "rule-a"}]
    other = run_cli(
        *args,
        "--type",
        "issue" if selection == "type" else "issue,warning",
        "--priority",
        "low" if selection == "priority" else "high",
        "--cursor",
        cursor,
    )

    assert (other.exit_code, other.stdout, [error["code"] for error in other.errors()]) == (
        2,
        b"",
        ["invalid_cursor"],
    )


def test_issues_is_described_as_a_list_command() -> None:
    listed = run_cli("commands")
    assert listed.exit_code == 0, listed.stderr
    (entry,) = [command for command in listed.json()["commands"] if command["name"] == "issues"]

    assert (entry["output"], entry["formats"]) == ("list", ["json", "jsonl", "table"])
    assert entry["fields"] == {
        "available": [
            "rule_id",
            "category",
            "issue_type",
            "priority",
            "affected_count",
            "description",
        ],
        "default": [
            "rule_id",
            "category",
            "issue_type",
            "priority",
            "affected_count",
            "description",
        ],
    }
    options = {option["name"]: option for option in entry["options"]}
    assert options.keys() == {
        "--type",
        "--priority",
        "--crawl",
        "--workspace",
        "--format",
        "--limit",
        "--cursor",
        "--fields",
    }
    assert (options["--crawl"]["global"], options["--crawl"]["default"]) == (True, "latest")
