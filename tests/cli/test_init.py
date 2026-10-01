"""`spider init` (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

import pytest

from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


@pytest.fixture
def shop(temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = temp_workspace.root / "shop"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


def test_first_run(shop: Path) -> None:
    result = run_cli("init")

    assert (result.exit_code, list(result.json().items())) == (
        0,
        [
            ("workspace", str(shop)),
            ("data_dir", str(shop / ".spider")),
            ("settings_file", str(shop / "spider.toml")),
            ("global", False),
            (
                "created",
                [
                    str(shop / ".spider"),
                    str(shop / ".spider" / ".gitignore"),
                    str(shop / ".spider" / "crawls"),
                    str(shop / "spider.toml"),
                ],
            ),
        ],
    )
