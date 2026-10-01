"""`spider commands` (010-add-workspace-and-cli-contract, cli-contract)."""

import tomllib
from pathlib import Path

from tests.support.cli import run_cli

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def project_version() -> str:
    with PYPROJECT.open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return version


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
