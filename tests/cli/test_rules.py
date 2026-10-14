"""`spider rules` (040-add-rules, rules; seam 1)."""

import json
import sys

import pytest

from tests.support.cli import run_cli, run_cli_process

GUIDANCE = ("description", "why_it_matters", "how_to_fix")


def test_first_rule_in_the_list() -> None:
    page = run_cli("rules", "list", "--limit", "1").json()

    assert (page["items"][0]["id"], page["items"][0]["category"], page["next_cursor"] is None) == (
        "internal-4xx",
        "response_codes",
        False,
    )


def test_every_rule_has_its_guidance() -> None:
    items = run_cli("rules", "list", "--limit", "50").json()["items"]

    assert [item["id"] for item in items if not all(item[key] for key in GUIDANCE)] == []


def test_show_a_rule_with_thresholds() -> None:
    result = run_cli("rules", "show", "title-too-long")
    rule = result.json()

    assert (
        result.exit_code,
        rule["category"],
        rule["issue_type"],
        rule["priority"],
        rule["thresholds"],
    ) == (
        0,
        "titles",
        "opportunity",
        "medium",
        {"max_chars": {"value": 60, "default": 60, "unit": "characters"}},
    )


def test_rule_without_thresholds() -> None:
    items = run_cli("rules", "list", "--limit", "50").json()["items"]

    assert [item["thresholds"] for item in items if item["id"] == "title-missing"] == [{}]


def test_unknown_rule_id() -> None:
    result = run_cli("rules", "show", "nope")
    (error,) = result.stderr_json_lines()

    assert (
        result.exit_code,
        error["code"],
        "nope" in error["message"],
        "spider rules list" in error["hint"],
    ) == (4, "rule_not_found", True, True)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_windows_console_output() -> None:
    stdout = run_cli_process("rules", "show", "title-too-long").stdout

    assert json.loads(stdout.decode("utf-8"))["id"] == "title-too-long"


def test_the_bare_group_lists_the_rules() -> None:
    assert run_cli("rules").json() == run_cli("rules", "list").json()
