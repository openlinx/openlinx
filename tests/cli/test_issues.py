"""Exercise list filters, paging and discovery through the public Issues Command."""

import os
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from openlinx.store.crawls import record_state
from openlinx.store.records import CrawlState, RuleRow, StopReason
from openlinx.store.writer import CrawlWriter
from tests.support.cli import run_cli, run_cli_process
from tests.support.clock import FakeClock
from tests.support.crawl_store import IssueExample, crawl_store
from tests.support.crawls import STARTED_AT, create_any_crawl, create_crawl_at, sha256_of
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


@pytest.fixture
def category_crawl(temp_workspace: TempWorkspace) -> Path:
    return crawl_store(
        temp_workspace,
        pages={
            "https://example.com/no-title": "<h1>Welcome</h1><h2>First section</h2>",
            "https://example.com/no-heading": "<title>Welcome</title><h2>First section</h2>",
        },
    )


@pytest.fixture
def issue_detail_crawl(temp_workspace: TempWorkspace) -> Path:
    return crawl_store(
        temp_workspace,
        example_issues=(
            ("title-missing", "issue", "high", 3),
            ("h1-missing", "warning", "medium", 1),
        ),
    )


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        pytest.param(("--category", "headings"), ["h1-missing"], id="headings-only"),
        pytest.param(
            ("--category", " TITLES,Headings "),
            ["title-missing", "h1-missing", "title-too-short", "title-same-as-h1"],
            id="comma-separated",
        ),
        pytest.param(
            ("--category", "HEADINGS", "--category", "titles"),
            ["title-missing", "h1-missing", "title-too-short", "title-same-as-h1"],
            id="repeatable",
        ),
        pytest.param(
            ("--category", "titles", "--type", "issue,warning", "--priority", "medium"),
            [],
            id="with-type-and-priority",
        ),
    ],
)
def test_filter_by_category(
    category_crawl: Path, filters: tuple[str, ...], expected: list[str]
) -> None:
    result = run_cli("issues", "--crawl", str(category_crawl), "--fields", "rule_id", *filters)

    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "total": len(expected),
        "items": [{"rule_id": rule_id} for rule_id in expected],
        "next_cursor": None,
    }


def test_a_cursor_belongs_to_its_normalised_categories(category_crawl: Path) -> None:
    args = ("issues", "--crawl", str(category_crawl), "--fields", "rule_id")
    first = run_cli(*args, "--category", "titles,headings", "--limit", "1")
    assert first.exit_code == 0, first.stderr
    page = first.json()
    assert (page["total"], page["items"]) == (4, [{"rule_id": "title-missing"}])
    cursor = page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    resumed = run_cli(
        *args,
        "--category",
        "HEADINGS",
        "--category",
        "titles,titles",
        "--cursor",
        cursor,
        "--limit",
        "3",
    )
    assert resumed.exit_code == 0, resumed.stderr
    assert resumed.json() == {
        "total": 4,
        "items": [
            {"rule_id": "h1-missing"},
            {"rule_id": "title-too-short"},
            {"rule_id": "title-same-as-h1"},
        ],
        "next_cursor": None,
    }

    changed = run_cli(*args, "--category", "headings", "--cursor", cursor)
    assert (changed.exit_code, changed.stdout, [error["code"] for error in changed.errors()]) == (
        2,
        b"",
        ["invalid_cursor"],
    )


def test_unknown_category_lists_accepted_values(category_crawl: Path) -> None:
    result = run_cli("issues", "--crawl", str(category_crawl), "--category", "titles,links")

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "invalid_value"
    assert error["details"]["accepted"] == [
        "response_codes",
        "security",
        "titles",
        "meta_descriptions",
        "headings",
        "canonicals",
        "directives",
        "content",
        "urls",
        "images",
    ]


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


def test_unknown_issue_type(temp_workspace: TempWorkspace, issue_crawl: Path) -> None:
    result = run_cli("issues", "--workspace", str(temp_workspace.root), "--type", "critical")

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error == result.stderr_json_lines()[-1]
    assert error["code"] == "invalid_value"
    assert error["details"]["flag"] == "--type"
    assert error["details"]["value"] == "critical"
    assert error["details"]["accepted"] == ["issue", "warning", "opportunity"]
    assert error["hint"].strip()


def test_issues_is_described_as_a_list_command() -> None:
    listed = run_cli("commands")
    assert listed.exit_code == 0, listed.stderr
    commands = listed.json()["commands"]
    (entry,) = [command for command in commands if command["name"] == "issues"]

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
    (argument,) = entry["arguments"]
    assert (argument["name"], argument["required"], argument["default"]) == ("rule_id", False, None)
    assert entry["fields_by_argument"] == {
        "rule_id": {"available": ["url", "detail"], "default": ["url", "detail"]},
    }
    assert all("fields_by_argument" not in command for command in commands if command is not entry)
    assert all(command["name"] != "issue" for command in commands)
    options = {option["name"]: option for option in entry["options"]}
    assert options.keys() == {
        "--category",
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


@pytest.mark.parametrize("rule_id", ["title-mising", "h2-missing"])
def test_unknown_rule_id_uses_the_selected_crawl(issue_detail_crawl: Path, rule_id: str) -> None:
    result = run_cli("issues", rule_id, "--crawl", str(issue_detail_crawl))

    assert (result.exit_code, result.stdout) == (4, b"")
    (error,) = result.errors()
    assert error["code"] == "rule_not_found"
    assert error["details"]["id"] == rule_id
    suggestions = error["details"]["suggestions"]
    assert suggestions
    assert set(suggestions) <= {"title-missing", "h1-missing"}
    if rule_id == "title-mising":
        assert suggestions[0] == "title-missing"
    assert "linx rules list" in error["hint"]


@pytest.mark.parametrize(
    ("flag", "value"),
    [("--type", "issue"), ("--priority", "high"), ("--category", "content"), ("--type", "")],
)
def test_list_filters_with_rule_id_fail_before_selecting_a_crawl(
    temp_workspace: TempWorkspace, flag: str, value: str
) -> None:
    missing = temp_workspace.root / "missing.sqlite"
    result = run_cli("issues", "title-missing", "--crawl", str(missing), f"{flag}={value}")

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "invalid_value"
    assert error["details"]["flag"] == flag
    message = error["message"].lower()
    hint = error["hint"].lower()
    assert flag in message
    assert "filter" in message
    assert "issue list" in message or "list of issues" in message
    assert "rule id" in hint
    assert any(word in hint for word in ("omit", "remove", "drop"))


@pytest.mark.parametrize(
    ("rule_args", "unknown"),
    [pytest.param((), "url", id="list"), pytest.param(("title-missing",), "rule_id", id="detail")],
)
def test_issue_fields_match_discovery(
    issue_detail_crawl: Path, rule_args: tuple[str, ...], unknown: str
) -> None:
    discovery = run_cli("commands")
    assert discovery.exit_code == 0, discovery.stderr
    (entry,) = [command for command in discovery.json()["commands"] if command["name"] == "issues"]
    fields = entry["fields_by_argument"]["rule_id"] if rule_args else entry["fields"]
    args = ("issues", *rule_args, "--crawl", str(issue_detail_crawl), "--limit", "1")

    default = run_cli(*args)
    all_fields = run_cli(*args, "--fields", "all")
    wrong_field = run_cli(*args, "--fields", unknown)

    assert default.exit_code == 0, default.stderr
    assert all_fields.exit_code == 0, all_fields.stderr
    assert [list(item) for item in default.json()["items"]] == [fields["default"]]
    assert [list(item) for item in all_fields.json()["items"]] == [fields["available"]]
    assert (wrong_field.exit_code, wrong_field.stdout) == (2, b"")
    (error,) = wrong_field.errors()
    assert error["code"] == "unknown_field"
    assert error["details"] == {"field": unknown, "available": fields["available"]}


def test_issue_detail_preserves_a_wide_recorded_threshold(temp_workspace: TempWorkspace) -> None:
    max_hops = 10**700 + 7
    recorded = RuleRow(
        id="redirect-chain",
        category="response_codes",
        issue_type="warning",
        priority="medium",
        applies_to="internal_urls",
        enabled=True,
        thresholds={"max_hops": max_hops},
        description="An Internal URL has a Redirect Chain longer than max_hops.",
        why_it_matters="Each redirect adds a request.",
        how_to_fix="Link directly to the destination.",
        reproduce_sql="SELECT id AS url_id, NULL AS detail FROM urls WHERE 0",
    )
    crawl = create_any_crawl(temp_workspace, rules=[recorded]).path
    with CrawlWriter(crawl, FakeClock()) as writer:
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=1)))

    result = run_cli_process(
        "issues",
        "redirect-chain",
        "--crawl",
        str(crawl),
        env={**os.environ, "PYTHONINTMAXSTRDIGITS": "640"},
    )

    assert result.exit_code == 0, result.stderr
    rule = result.json()["rule"]
    assert rule["rule_id"] == "redirect-chain"
    assert rule["thresholds"] == {"max_hops": max_hops}
    assert type(rule["thresholds"]["max_hops"]) is int


@pytest.mark.parametrize(
    ("rule_args", "projection", "first_item", "remaining_fields", "remaining_items", "total"),
    [
        pytest.param(
            (),
            " affected_count , rule_id, affected_count ",
            {"affected_count": 3, "rule_id": "title-missing"},
            "rule_id",
            [{"rule_id": "h1-missing"}],
            2,
            id="list",
        ),
        pytest.param(
            ("title-missing",),
            " detail , url, detail ",
            {"detail": None, "url": "https://example.com/title-missing/0"},
            "url",
            [
                {"url": "https://example.com/title-missing/1"},
                {"url": "https://example.com/title-missing/2"},
            ],
            3,
            id="detail",
        ),
    ],
)
def test_projection_can_change_between_issue_pages(
    issue_detail_crawl: Path,
    rule_args: tuple[str, ...],
    projection: str,
    first_item: dict[str, Any],
    remaining_fields: str,
    remaining_items: list[dict[str, Any]],
    total: int,
) -> None:
    args = ("issues", *rule_args, "--crawl", str(issue_detail_crawl))
    first = run_cli(*args, "--limit", "1", "--fields", projection)
    assert first.exit_code == 0, first.stderr
    first_page = first.json()
    assert (first_page["total"], first_page["items"]) == (total, [first_item])
    assert list(first_page["items"][0]) == list(first_item)
    cursor = first_page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    last = run_cli(*args, "--limit", "2", "--fields", remaining_fields, "--cursor", cursor)
    count = run_cli(*args, "--limit", "0", "--cursor", cursor)
    assert last.exit_code == 0, last.stderr
    assert count.exit_code == 0, count.stderr
    last_page, count_page = last.json(), count.json()
    assert (last_page["total"], last_page["items"], last_page["next_cursor"]) == (
        total,
        remaining_items,
        None,
    )
    assert (count_page["total"], count_page["items"], count_page["next_cursor"]) == (
        total,
        [],
        None,
    )
    if rule_args:
        assert first_page["rule"]["rule_id"] == "title-missing"
        assert first_page["rule"] == last_page["rule"] == count_page["rule"]
    else:
        assert all("rule" not in page for page in (first_page, last_page, count_page))


def test_issue_cursors_are_bound_to_the_form_crawl_and_rule(
    temp_workspace: TempWorkspace, issue_detail_crawl: Path
) -> None:
    selected = ("--crawl", str(issue_detail_crawl), "--limit", "1")
    issue_list = run_cli("issues", *selected)
    detail = run_cli("issues", "title-missing", *selected)
    assert issue_list.exit_code == 0, issue_list.stderr
    assert detail.exit_code == 0, detail.stderr
    list_cursor = issue_list.json()["next_cursor"]
    detail_cursor = detail.json()["next_cursor"]
    assert isinstance(list_cursor, str)
    assert list_cursor
    assert isinstance(detail_cursor, str)
    assert detail_cursor
    other = create_crawl_at(temp_workspace, "2026-09-27T15:00:00.000Z", "next").path

    for args in (
        ("title-missing", *selected, "--cursor", list_cursor),
        (*selected, "--cursor", detail_cursor),
        ("h1-missing", *selected, "--cursor", detail_cursor),
        ("title-missing", "--crawl", str(other), "--cursor", detail_cursor),
    ):
        wrong = run_cli("issues", *args)
        assert (wrong.exit_code, wrong.stdout) == (2, b"")
        (error,) = wrong.errors()
        assert error["code"] == "invalid_cursor"


@pytest.mark.parametrize(
    ("state", "stop_reason"),
    [
        pytest.param("completed", None, id="completed"),
        pytest.param("stopped", "max_urls", id="stopped"),
    ],
)
@pytest.mark.parametrize(
    "rule_args", [pytest.param((), id="list"), pytest.param(("title-missing",), id="detail")]
)
def test_issues_reports_a_crawl_missing_the_issues_view(
    temp_workspace: TempWorkspace,
    state: CrawlState,
    stop_reason: StopReason | None,
    rule_args: tuple[str, ...],
) -> None:
    workspace = ("--workspace", str(temp_workspace.root))
    initialized = run_cli("init", *workspace)
    assert initialized.exit_code == 0, initialized.stderr
    file = create_any_crawl(temp_workspace).path
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(record_state(state, STARTED_AT + timedelta(seconds=1), stop_reason))

    healthy = run_cli("issues", *rule_args, *workspace)
    assert healthy.exit_code == 0, healthy.stderr
    assert healthy.json()["total"] == 0
    if rule_args:
        assert healthy.json()["rule"]["rule_id"] == "title-missing"

    with closing(sqlite3.connect(file)) as connection:
        connection.execute("DROP VIEW issues")
        connection.commit()
    before = sha256_of(file)

    broken = run_cli("issues", *rule_args, *workspace)

    assert sha256_of(file) == before
    assert (broken.exit_code, broken.stdout) == (6, b""), broken.stderr
    (error,) = broken.errors()
    assert error["code"] == "crawl_file_invalid"
    assert error["details"]["file"] == str(file)
