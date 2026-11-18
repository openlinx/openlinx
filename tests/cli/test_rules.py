"""Verify the Rules catalogue through the CLI."""

import pytest

from tests.support.cli import run_cli

GUIDANCE = ("description", "why_it_matters", "how_to_fix")


def test_first_rule_in_the_list() -> None:
    result = run_cli("rules", "list", "--limit", "1")

    assert result.exit_code == 0, result.stderr
    page = result.json()
    (rule,) = page["items"]
    assert (rule["id"], rule["category"]) == ("internal-4xx", "response_codes")
    cursor = page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    following = run_cli("rules", "list", "--fields", "id", "--limit", "1", "--cursor", cursor)
    assert following.exit_code == 0, following.stderr
    assert following.json()["items"] == [{"id": "internal-5xx"}]


def test_every_rule_has_its_guidance() -> None:
    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    assert items
    assert [item["id"] for item in items if not all(item[key] for key in GUIDANCE)] == []


def test_show_a_rule_with_thresholds() -> None:
    result = run_cli("rules", "show", "title-too-long")

    assert result.exit_code == 0, result.stderr
    rule = result.json()
    assert (rule["id"], rule["category"], rule["issue_type"], rule["priority"]) == (
        "title-too-long",
        "titles",
        "opportunity",
        "medium",
    )
    assert rule["applies_to"] == "internal_pages"
    assert rule["thresholds"] == {"max_chars": {"value": 60, "default": 60, "unit": "characters"}}
    assert rule["description"] == "A Page's first title is longer than max_chars characters."
    assert rule["why_it_matters"] == (
        "Search engines cut a long title short in their results, so its end, often the brand or "
        "what sets the page apart, is not shown."
    )
    assert rule["how_to_fix"] == (
        "Shorten the title to the limit, with the words that describe the page first."
    )


def test_rule_without_thresholds() -> None:
    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    assert [item for item in items if item["id"] == "title-missing"] == [
        {
            "id": "title-missing",
            "category": "titles",
            "issue_type": "issue",
            "priority": "high",
            "applies_to": "internal_pages",
            "thresholds": {},
            "description": "A Page has no title, or its first title is empty.",
            "why_it_matters": (
                "A descriptive title helps people identify the Page in search results "
                "and browser tabs."
            ),
            "how_to_fix": (
                "If the Page has no title, add a <title> element to its <head>. If the first "
                "<title> is empty, fill it in. Use words that describe the Page and set it "
                "apart from the site's other Pages."
            ),
        }
    ]


def test_unknown_rule_id() -> None:
    result = run_cli("rules", "show", "nope")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (4, "rule_not_found")
    assert "nope" in error["message"]
    assert "linx rules list" in error["hint"]
    assert result.stdout == b""


def test_show_matches_the_rule_in_the_catalogue() -> None:
    first = run_cli("rules", "list", "--fields", "id,thresholds", "--limit", "2")
    assert first.exit_code == 0, first.stderr
    page = first.json()
    assert page["items"] == [
        {"id": "internal-4xx", "thresholds": {}},
        {"id": "internal-5xx", "thresholds": {}},
    ]
    cursor = page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    following = run_cli("rules", "list", "--cursor", cursor, "--limit", "2")
    missing = run_cli("rules", "show", "title-missing")
    too_long = run_cli("rules", "show", "title-too-long")
    assert following.exit_code == 0, following.stderr
    assert missing.exit_code == 0, missing.stderr
    assert too_long.exit_code == 0, too_long.stderr
    assert following.json()["items"] == [missing.json(), too_long.json()]


def test_the_bare_group_lists_the_rules() -> None:
    bare = run_cli("rules")
    explicit = run_cli("rules", "list")

    assert bare.exit_code == explicit.exit_code == 0
    assert bare.stdout == explicit.stdout


def test_the_group_is_visible_in_help() -> None:
    root_help = run_cli("--help")
    group_help = run_cli("rules", "--help")

    assert root_help.exit_code == group_help.exit_code == 0
    assert b"rules" in root_help.stdout
    assert b"list" in group_help.stdout


@pytest.mark.parametrize(
    ("args", "hint"),
    [
        pytest.param(
            ("--format=json", "list"),
            "Put --format after the Command name: linx rules list --format ...",
            id="before-list",
        ),
        pytest.param(
            ("--limit", "1"),
            "Put --limit after the Command name: linx rules list --limit ...",
            id="bare-group",
        ),
    ],
)
def test_options_follow_the_full_command_name(args: tuple[str, ...], hint: str) -> None:
    result = run_cli("rules", *args)
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (2, "usage_error")
    assert error["hint"] == hint


def test_root_option_stays_at_the_root() -> None:
    result = run_cli("rules", "--version")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (2, "usage_error")
    assert error["hint"] == "Put --version before the Command name: linx --version"
