"""Verify the Rules catalogue through the CLI."""

import json
import subprocess
import sys
from tempfile import TemporaryFile

import pytest

from tests.support.cli import CLI_PROCESS_TIMEOUT, run_cli
from tests.support.processes import console_process, python_command

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

    following = run_cli(
        "rules", "list", "--fields", "id,thresholds", "--limit", "1", "--cursor", cursor
    )
    assert following.exit_code == 0, following.stderr
    assert following.json()["items"] == [{"id": "internal-5xx", "thresholds": {}}]


def test_every_rule_has_its_guidance() -> None:
    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    assert items
    assert [
        item["id"]
        for item in items
        if not all(isinstance(item[key], str) and item[key].strip() for key in GUIDANCE)
    ] == []


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


def test_rule_without_thresholds() -> None:
    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    (rule,) = (item for item in items if item["id"] == "title-missing")
    assert (rule["category"], rule["issue_type"], rule["priority"], rule["applies_to"]) == (
        "titles",
        "issue",
        "high",
        "internal_pages",
    )
    assert rule["thresholds"] == {}


def test_unknown_rule_id() -> None:
    result = run_cli("rules", "show", "nope")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (4, "rule_not_found")
    assert "nope" in error["message"]
    assert "linx rules list" in error["hint"]
    assert result.stdout == b""


@pytest.mark.skipif(sys.platform != "win32", reason="requires a Windows console")
def test_windows_console_output() -> None:
    command = python_command("-m", "openlinx", "rules", "show", "title-too-long")
    # Change the code page in a separate console so it cannot affect the test runner.
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        with console_process(
            f"chcp 1251 && {subprocess.list2cmdline(command.argv)}",
            env=command.env,
            stdout=stdout.fileno(),
            stderr=stderr.fileno(),
        ) as process:
            process.communicate(timeout=CLI_PROCESS_TIMEOUT)
        stdout.seek(0)
        stderr.seek(0)
        code_page, _, output = stdout.read().partition(b"\n")
        errors = stderr.read()

    assert process.returncode == 0, (code_page, errors)
    # The first line is chcp's localized confirmation. The rest is the Command's JSON.
    assert b"1251" in code_page, code_page
    rule = json.loads(output.decode("utf-8"))
    assert isinstance(rule, dict)
    assert rule["id"] == "title-too-long"
    assert output.endswith(b"}\n")
    assert b"\r" not in output


@pytest.mark.parametrize("rule_id", ["title-missing", "title-too-long"])
def test_show_matches_the_rule_in_the_catalogue(rule_id: str) -> None:
    listed = run_cli("rules", "list", "--limit", "50")
    shown = run_cli("rules", "show", rule_id)

    assert listed.exit_code == 0, listed.stderr
    assert shown.exit_code == 0, shown.stderr
    (item,) = (item for item in listed.json()["items"] if item["id"] == rule_id)
    assert item == shown.json()


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
        pytest.param(
            ("--format=table", "show", "title-too-long"),
            "Put --format after the Command name: linx rules show --format ...",
            id="before-show",
        ),
    ],
)
def test_options_follow_the_full_command_name(args: tuple[str, ...], hint: str) -> None:
    result = run_cli("rules", *args)
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (2, "usage_error")
    assert error["hint"] == hint


@pytest.mark.parametrize(
    ("args", "option"),
    [
        pytest.param(("--bogus",), "--bogus", id="unknown-for-bare-group"),
        pytest.param(("--bogus", "list"), "--bogus", id="unknown-for-list"),
        pytest.param(("--limit", "1", "show", "title-too-long"), "--limit", id="list-only"),
    ],
)
def test_an_unaccepted_group_option_has_no_placement_hint(
    args: tuple[str, ...], option: str
) -> None:
    result = run_cli("rules", *args)

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["code"], error["message"], error["hint"]) == (
        "usage_error",
        f"No such option: {option}",
        None,
    )


def test_root_option_stays_at_the_root() -> None:
    result = run_cli("rules", "--version")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"]) == (2, "usage_error")
    assert error["hint"] == "Put --version before the Command name: linx --version"
