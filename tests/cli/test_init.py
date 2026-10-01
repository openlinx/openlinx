"""`spider init` (010-add-workspace-and-cli-contract, workspace)."""

import sys
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


def test_second_run_creates_nothing(shop: Path) -> None:
    run_cli("init")

    result = run_cli("init")

    assert (result.exit_code, result.json()["created"]) == (0, [])


def test_existing_settings_file_is_kept_byte_for_byte(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b'[example]\nlevel = "high"\n')

    run_cli("init")

    assert (shop / "spider.toml").read_bytes() == b'[example]\nlevel = "high"\n'


def test_target_folder_is_created(temp_workspace: TempWorkspace) -> None:
    site = temp_workspace.home / "work" / "new" / "site"

    result = run_cli("init", "--workspace", str(site))

    assert (result.exit_code, (site / ".spider" / "crawls").is_dir()) == (0, True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths only")
def test_workspace_written_with_forward_slashes_on_windows(temp_workspace: TempWorkspace) -> None:
    home = temp_workspace.home

    result = run_cli("init", "--workspace", home.as_posix() + "/work/b")

    assert result.json()["workspace"] == str(home) + r"\work\b"
