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
