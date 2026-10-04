"""`spider commands` (010-add-workspace-and-cli-contract, cli-contract)."""

from typing import Any

from tests.support.app import example_app
from tests.support.cli import run_cli
from tests.support.project import project_version


def test_the_command_lists_itself() -> None:
    names = [entry["name"] for entry in run_cli("commands").json()["commands"]]

    assert "commands" in names


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


def _entry(description: dict[str, Any], name: str) -> dict[str, Any]:
    entry: dict[str, Any] = next(c for c in description["commands"] if c["name"] == name)
    return entry
