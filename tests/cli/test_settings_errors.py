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
