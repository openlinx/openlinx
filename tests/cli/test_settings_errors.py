"""Invalid settings name the offending key (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

import pytest

from tests.support.app import example_app
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


@pytest.fixture
def shop(temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = temp_workspace.root / "shop"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


def test_invalid_value(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b'[example]\nlevel = "medium"\n')

    result = run_cli("init", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        error["details"]["file"],
        error["details"]["errors"][0]["key"],
    ) == (3, "settings_invalid", str(shop / "spider.toml"), "example.level")


def test_unknown_key_with_a_suggestion(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b'[example]\nlevl = "high"\n')

    error = run_cli("init", app=example_app()).stderr_json_lines()[-1]

    assert (error["details"]["errors"][0]["key"], "level" in (error["hint"] or "")) == (
        "example.levl",
        True,
    )


def test_output_flags_have_no_settings_key(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b'[output]\nformat = "table"\n')

    result = run_cli("init", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["details"]["errors"][0]["key"]) == (
        3,
        "settings_invalid",
        "output",
    )


def test_toml_syntax_error(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[example\n")

    first = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"][0]

    assert (first["key"], first["line"]) == (None, 1)


def test_every_problem_is_listed(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[example]\nlevel = 1\n[crawler]\n")

    errors = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"]

    assert [error["key"] for error in errors] == ["example.level", "crawler"]


def test_problems_are_listed_in_file_order(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[crawler]\n[example]\nlevel = 1\n")

    errors = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"]

    assert [error["key"] for error in errors] == ["crawler", "example.level"]


def test_nothing_is_created_when_the_settings_are_invalid(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[example\n")

    run_cli("init", app=example_app())

    assert (shop / ".spider").exists() is False


def test_commands_without_a_workspace_ignore_the_settings_file(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[example\n")

    assert run_cli("commands", app=example_app()).exit_code == 0
