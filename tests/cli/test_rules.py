"""Verify the Rules catalogue through the CLI."""

import json
import re
import subprocess
import sys
from tempfile import TemporaryFile

import pytest

from tests.support.cli import CLI_PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.processes import console_process, python_command
from tests.support.workspace import TempWorkspace

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


def test_show_a_rule_with_thresholds(temp_workspace: TempWorkspace) -> None:
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


def test_override_shown_by_the_rules_command(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")

    shown = run_cli_process("rules", "show", "title-too-long")
    listed = run_cli("rules", "list", "--limit", "50")

    assert shown.exit_code == 0, shown.stderr
    assert listed.exit_code == 0, listed.stderr
    (item,) = (item for item in listed.json()["items"] if item["id"] == "title-too-long")
    expected = {"max_chars": {"value": 70, "default": 60, "unit": "characters"}}
    assert shown.json()["thresholds"] == expected
    assert item["thresholds"] == expected


def test_rules_use_the_explicit_workspace(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")
    other = temp_workspace.root / "other"
    other.mkdir()
    (other / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 0\n")

    shown = run_cli("rules", "show", "title-too-long", "--workspace", "other")
    listed = run_cli("rules", "list", "--workspace", "other", "--limit", "50")

    assert shown.exit_code == 0, shown.stderr
    assert listed.exit_code == 0, listed.stderr
    (item,) = (item for item in listed.json()["items"] if item["id"] == "title-too-long")
    expected = {"max_chars": {"value": 0, "default": 60, "unit": "characters"}}
    assert shown.json()["thresholds"] == expected
    assert item["thresholds"] == expected


def test_disabled_rule_is_listed(temp_workspace: TempWorkspace) -> None:
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_bytes(b"[rules.url-parameters]\nenabled = false\n")

    listed = run_cli("rules", "list", "--limit", "50")
    shown = run_cli("rules", "show", "url-parameters")

    assert listed.exit_code == 0, listed.stderr
    assert shown.exit_code == 0, shown.stderr
    items = listed.json()["items"]
    (item,) = (item for item in items if item["id"] == "url-parameters")
    assert item["enabled"] is False
    assert [item["id"] for item in items if item["enabled"] is not True] == ["url-parameters"]
    document = shown.json()
    assert document["enabled"] is False
    assert document == item
    assert (item["category"], item["issue_type"], item["priority"], item["applies_to"]) == (
        "urls",
        "opportunity",
        "low",
        "internal_pages",
    )
    assert item["thresholds"] == {}


def test_rules_are_enabled_by_default(temp_workspace: TempWorkspace) -> None:
    listed = run_cli("rules", "list", "--limit", "50")
    shown = run_cli("rules", "show", "url-parameters")

    assert listed.exit_code == 0, listed.stderr
    assert shown.exit_code == 0, shown.stderr
    items = listed.json()["items"]
    assert "url-parameters" in {item["id"] for item in items}
    assert [item["id"] for item in items if item["enabled"] is not True] == []
    assert shown.json()["enabled"] is True


def test_explicit_workspace_can_enable_a_rule(temp_workspace: TempWorkspace) -> None:
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_bytes(b"[rules.url-parameters]\nenabled = false\n")
    other = temp_workspace.root / "other"
    other.mkdir()
    (other / "openlinx.toml").write_bytes(b"[rules.url-parameters]\nenabled = true\n")

    listed = run_cli("rules", "list", "--workspace", "other", "--fields", "id,enabled")
    shown = run_cli("rules", "show", "url-parameters", "--workspace", "other")

    assert listed.exit_code == 0, listed.stderr
    assert shown.exit_code == 0, shown.stderr
    (item,) = (item for item in listed.json()["items"] if item["id"] == "url-parameters")
    assert set(item) == {"id", "enabled"}
    assert item["enabled"] is True
    assert shown.json()["enabled"] is True


def test_misspelt_rule_id(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-to-long]\n")

    result = run_cli("rules", "list")

    assert result.exit_code == 3
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert error["code"] == "settings_invalid"
    assert error["details"]["errors"][0]["key"] == "rules.title-to-long"
    assert "title-too-long" in re.findall(r"[\w-]+", error.get("hint") or "")


def test_unknown_key(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.h2-missing]\nmax_chars = 10\n")

    result = run_cli("rules", "list")

    assert result.exit_code == 3
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert error["code"] == "settings_invalid"
    assert error["details"]["errors"][0]["key"] == "rules.h2-missing.max_chars"


def test_h2_missing_is_listed_as_a_heading_rule(temp_workspace: TempWorkspace) -> None:
    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    ids = [item["id"] for item in items]
    assert "h2-missing" in ids
    assert ids.index("title-too-long") < ids.index("h2-missing") < ids.index("url-parameters")
    (item,) = (item for item in items if item["id"] == "h2-missing")
    assert (item["category"], item["issue_type"], item["priority"], item["applies_to"]) == (
        "headings",
        "opportunity",
        "low",
        "internal_pages",
    )
    assert item["thresholds"] == {}
    assert item["enabled"] is True


@pytest.mark.parametrize(
    ("settings", "value"),
    [
        pytest.param(b"", 200, id="default"),
        pytest.param(b"[rules.low-word-count]\nmin_words = 0\n", 0, id="zero"),
        pytest.param(b"[rules.low-word-count]\nmin_words = 300\n", 300, id="override"),
    ],
)
def test_low_word_count_is_listed_as_a_content_rule(
    temp_workspace: TempWorkspace, settings: bytes, value: int
) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(settings)

    result = run_cli("rules", "list", "--limit", "50")

    assert result.exit_code == 0, result.stderr
    items = result.json()["items"]
    (item,) = (item for item in items if item["id"] == "low-word-count")
    ids = [item["id"] for item in items]
    assert ids.index("h2-missing") < ids.index("low-word-count") < ids.index("url-parameters")
    assert (item["category"], item["issue_type"], item["priority"], item["applies_to"]) == (
        "content",
        "opportunity",
        "medium",
        "internal_pages",
    )
    assert item["enabled"] is True
    assert item["thresholds"] == {"min_words": {"value": value, "default": 200, "unit": "words"}}


def test_a_rule_enabled_setting_requires_a_boolean(temp_workspace: TempWorkspace) -> None:
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_bytes(b'[rules.internal-4xx]\nenabled = "false"\n')

    result = run_cli("rules", "show", "internal-4xx")

    assert result.exit_code == 3
    (error,) = result.stderr_json_lines()
    assert error["code"] == "settings_invalid"
    (problem,) = error["details"]["errors"]
    assert problem["key"] == "rules.internal-4xx.enabled"


def test_a_rules_cursor_belongs_to_its_workspace(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")
    (temp_workspace.root / "other").mkdir()
    first = run_cli("rules", "list", "--limit", "1")
    assert first.exit_code == 0, first.stderr
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    same = run_cli("rules", "list", "--workspace", ".", "--cursor", cursor, "--fields", "id")
    other = run_cli("rules", "list", "--workspace", "other", "--cursor", cursor)

    assert same.exit_code == 0, same.stderr
    assert {"id": "title-too-long"} in same.json()["items"]
    assert other.exit_code == 2, other.stdout
    assert other.stderr_json_lines()[-1]["code"] == "invalid_cursor"


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
