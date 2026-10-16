"""`spider commands` (010-add-workspace-and-cli-contract, cli-contract)."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.support.app import example_app
from tests.support.cli import run_cli, run_cli_process
from tests.support.project import project_version

CONTRACT = Path(__file__).resolve().parents[1] / "contract" / "commands"


def test_the_command_lists_itself() -> None:
    names = [entry["name"] for entry in run_cli("commands").json()["commands"]]

    assert "commands" in names


def test_a_command_in_a_group_is_listed_by_its_full_path() -> None:
    names = [entry["name"] for entry in run_cli("commands").json()["commands"]]

    assert ("rules list" in names, "rules" in names) == (True, False)


def test_tool_is_spider_with_the_project_version() -> None:
    tool = run_cli("commands").json()["tool"]

    assert tool == {"name": "spider", "version": project_version()}


def test_the_exit_code_table_is_self_described() -> None:
    exit_codes = run_cli("commands").json()["exit_codes"]

    assert [(entry["code"], entry["name"]) for entry in exit_codes] == [
        (0, "ok"),
        (1, "failed"),
        (2, "usage"),
        (3, "config"),
        (4, "not_found"),
        (5, "busy"),
        (6, "incompatible"),
        (7, "io"),
        (8, "network"),
        (70, "internal"),
        (130, "interrupted"),
    ]


def test_global_flags_of_init() -> None:
    entry = _entry(run_cli("commands").json(), "init")
    flags = {option["name"]: option["global"] for option in entry["options"]}

    assert (flags.get("--workspace"), flags.get("--format")) == (True, True)


def test_entry_of_a_document_command() -> None:
    entry = _entry(run_cli("commands").json(), "init")

    assert (entry["output"], entry["events"], entry["formats"], entry["fields"]) == (
        "document",
        False,
        ["json", "table"],
        None,
    )


def test_entry_of_a_list_command() -> None:
    entry = _entry(run_cli("commands", app=example_app()).json(), "example-list")

    assert (entry["output"], entry["formats"], entry["fields"]) == (
        "list",
        ["json", "jsonl", "table"],
        {"available": ["n", "sq"], "default": ["n"]},
    )


def test_the_issue_list_and_one_issue_are_described_apart() -> None:
    description = run_cli("commands").json()
    listed, one = _entry(description, "issues"), _entry(description, "issue")

    assert (
        [a["name"] for a in listed["arguments"]],
        [a["name"] for a in one["arguments"]],
        one["fields"],
    ) == (
        [],
        ["rule_id"],
        {"available": ["url", "detail"], "default": ["url", "detail"]},
    )


def test_option_details() -> None:
    entry = _entry(run_cli("commands").json(), "init")
    option = next(option for option in entry["options"] if option["name"] == "--workspace")

    assert {key: option.get(key) for key in ("type", "default", "global", "setting", "secret")} == {
        "type": "path",
        "default": None,
        "global": True,
        "setting": None,
        "secret": False,
    }


def test_a_secret_option_inherits_from_its_setting() -> None:
    options = _options(run_cli("commands", app=example_app()).json(), "example-settings")

    assert [
        (options[name]["setting"], options[name]["secret"]) for name in ("--token", "--level")
    ] == [
        ("example.token", True),
        ("example.level", False),
    ]


def test_a_secret_option_without_a_setting() -> None:
    option = _options(run_cli("commands", app=example_app()).json(), "example-settings")[
        "--api-key"
    ]

    assert (option["setting"], option["secret"]) == (None, True)


def test_error_codes_of_this_change() -> None:
    diagnostics = {d["code"]: d for d in run_cli("commands").json()["diagnostics"]}
    expected = {
        "usage_error": 2,
        "invalid_value": 2,
        "unknown_field": 2,
        "invalid_cursor": 2,
        "settings_invalid": 3,
        "workspace_not_found": 4,
        "workspace_not_writable": 7,
        "internal_error": 70,
        "interrupted": 130,
    }

    assert {code: diagnostics[code]["exit_code"] for code in expected} == expected


def test_store_codes_are_self_described() -> None:
    diagnostics = {d["code"]: d for d in run_cli("commands").json()["diagnostics"]}
    expected = {
        "no_crawls": 4,
        "crawl_not_found": 4,
        "crawl_busy": 5,
        "crawl_file_invalid": 6,
        "crawl_schema_too_new": 6,
        "crawl_not_writable": 7,
        "unknown_table": 2,
        "store_wal_unavailable": None,
    }

    assert {code: diagnostics[code]["exit_code"] for code in expected} == expected


def test_rule_codes_are_self_described() -> None:
    diagnostics = {d["code"]: d for d in run_cli("commands").json()["diagnostics"]}

    assert (diagnostics["rule_not_found"]["level"], diagnostics["rule_not_found"]["exit_code"]) == (
        "error",
        4,
    )


def test_warning_and_info_codes_of_this_change() -> None:
    diagnostics = {d["code"]: d for d in run_cli("commands").json()["diagnostics"]}

    assert [
        (diagnostics[code]["level"], diagnostics[code]["exit_code"])
        for code in ("workspace_nested", "more_items")
    ] == [("warning", None), ("info", None)]


def test_naming_rule_for_input_errors() -> None:
    diagnostics = run_cli("commands").json()["diagnostics"]

    assert [
        (d["code"], d["exit_code"])
        for d in diagnostics
        if d["code"].startswith(("invalid_", "unknown_")) or d["code"] == "usage_error"
        if d["exit_code"] != 2
    ] + [
        (d["code"], d["exit_code"])
        for d in diagnostics
        if d["code"].endswith("_not_found") or d["code"] == "no_crawls"
        if d["exit_code"] != 4
    ] == []


def test_the_proxy_variables_are_the_one_exception() -> None:
    environment = run_cli("commands").json()["environment"]

    assert [entry["names"] for entry in environment] == [["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]]


def test_detection_signals_change_nothing() -> None:
    without = {k: v for k, v in os.environ.items() if k != "CODEX_SANDBOX_NETWORK_DISABLED"}
    plain = run_cli_process("commands", env=without)
    signalled = run_cli_process("commands", env={**without, "CODEX_SANDBOX_NETWORK_DISABLED": "1"})

    assert (signalled.stdout == plain.stdout, plain.exit_code, signalled.exit_code) == (True, 0, 0)


@pytest.mark.parametrize("name", ["init", "commands"])
def test_same_description_on_every_os(name: str) -> None:
    expected = json.loads((CONTRACT / f"{name}.json").read_text(encoding="utf-8"))

    # Compared as compact JSON, so the key order counts too.
    assert json.dumps(_entry(run_cli("commands").json(), name)) == json.dumps(expected)


def _entry(description: dict[str, Any], name: str) -> dict[str, Any]:
    entry: dict[str, Any] = next(c for c in description["commands"] if c["name"] == name)
    return entry


def _options(description: dict[str, Any], name: str) -> dict[str, Any]:
    return {option["name"]: option for option in _entry(description, name)["options"]}
