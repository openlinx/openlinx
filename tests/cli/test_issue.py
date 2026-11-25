"""Exercise the Issue detail Command's metadata, projection and diagnostics."""

from pathlib import Path

import pytest

from tests.support.cli import run_cli
from tests.support.crawl_store import crawl_store
from tests.support.workspace import TempWorkspace


@pytest.fixture
def detail_crawl(temp_workspace: TempWorkspace) -> Path:
    return crawl_store(
        temp_workspace,
        pages={
            "https://example.com/a": "<h1>First</h1>",
            "https://example.com/b": "<h1>Second</h1>",
            "https://example.com/gone": None,
        },
    )


def test_unknown_rule_id(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        example_issues=(
            ("title-missing", "issue", "high", 1),
            ("title-missing-legacy", "issue", "high", 1),
        ),
    )

    result = run_cli("issue", "title-mising", "--crawl", str(file))

    assert (result.exit_code, result.stdout) == (4, b"")
    (error,) = result.errors()
    assert error["code"] == "rule_not_found"
    assert error["details"]["id"] == "title-mising"
    assert error["details"]["suggestions"] == ["title-missing", "title-missing-legacy"]
    assert "linx rules list" in error["hint"]


def test_issue_commands_publish_separate_field_sets() -> None:
    result = run_cli("commands", "--format", "json")

    assert result.exit_code == 0, result.stderr
    commands = {entry["name"]: entry for entry in result.json()["commands"]}
    plural = ["rule_id", "category", "issue_type", "priority", "affected_count", "description"]
    assert (commands["issues"]["output"], commands["issues"]["fields"]) == (
        "list",
        {"available": plural, "default": plural},
    )
    assert commands["issues"]["arguments"] == []
    detail = commands["issue"]
    assert (detail["output"], detail["formats"], detail["fields"]) == (
        "list",
        ["json", "jsonl", "table"],
        {"available": ["url", "detail"], "default": ["url", "detail"]},
    )
    (argument,) = detail["arguments"]
    assert (argument["name"], argument["required"], argument["variadic"]) == (
        "rule_id",
        True,
        False,
    )
    assert {option["name"] for option in detail["options"]} == {
        "--workspace",
        "--crawl",
        "--format",
        "--limit",
        "--cursor",
        "--fields",
    }


def test_projecting_affected_urls_keeps_the_rule_header(detail_crawl: Path) -> None:
    args = ("issue", "internal-4xx", "--crawl", str(detail_crawl))
    full = run_cli(*args)
    projected = run_cli(*args, "--fields", "url")

    assert full.exit_code == 0, full.stderr
    assert projected.exit_code == 0, projected.stderr
    assert full.json()["rule"]["rule_id"] == "internal-4xx"
    assert full.json()["items"] == [
        {"url": "https://example.com/gone", "detail": {"status_code": 404}}
    ]
    assert projected.json() == {
        "rule": full.json()["rule"],
        "total": 1,
        "items": [{"url": "https://example.com/gone"}],
        "next_cursor": None,
    }


def test_a_cursor_is_reused_with_the_other_issue_command(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        example_issues=(
            ("title-missing", "issue", "high", 2),
            ("internal-4xx", "issue", "high", 1),
        ),
    )
    crawl = ("--crawl", str(file), "--limit", "1")
    listing = run_cli("issues", *crawl)
    detail = run_cli("issue", "title-missing", *crawl)
    assert listing.exit_code == 0, listing.stderr
    assert detail.exit_code == 0, detail.stderr
    assert (listing.json()["total"], listing.json()["items"][0]["rule_id"]) == (2, "title-missing")
    assert (detail.json()["total"], detail.json()["items"]) == (
        2,
        [{"url": "https://example.com/title-missing/0", "detail": None}],
    )
    list_cursor = listing.json()["next_cursor"]
    detail_cursor = detail.json()["next_cursor"]
    assert isinstance(list_cursor, str)
    assert list_cursor
    assert isinstance(detail_cursor, str)
    assert detail_cursor

    for other in (
        run_cli("issue", "title-missing", *crawl, "--cursor", list_cursor),
        run_cli("issues", *crawl, "--cursor", detail_cursor),
    ):
        assert (other.exit_code, other.stdout) == (2, b"")
        (error,) = other.errors()
        assert error["code"] == "invalid_cursor"
