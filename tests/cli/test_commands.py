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
