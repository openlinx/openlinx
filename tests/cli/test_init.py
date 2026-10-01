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


def test_files_of_a_new_local_workspace(shop: Path) -> None:
    run_cli("init")

    entries = sorted(path.relative_to(shop).as_posix() for path in shop.rglob("*"))

    assert entries == [".spider", ".spider/.gitignore", ".spider/crawls", "spider.toml"]


def test_data_folder_ignores_its_own_contents(shop: Path) -> None:
    run_cli("init")

    assert (shop / ".spider" / ".gitignore").read_bytes() == (
        b"# Created by spider: crawl data is not committed.\n*\n"
    )
