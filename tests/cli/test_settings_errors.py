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
