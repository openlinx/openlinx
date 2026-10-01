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


def test_initialising_the_home_folder(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = temp_workspace.home
    monkeypatch.chdir(home)

    result = run_cli("init").json()

    assert (result["global"], result["settings_file"]) == (
        True,
        str(home / ".spider" / "spider.toml"),
    )


@pytest.fixture
def blog_in_shop(shop: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (shop / ".spider").mkdir()
    blog = shop / "blog"
    blog.mkdir()
    monkeypatch.chdir(blog)
    return blog


def test_nested_workspace_warning(shop: Path, blog_in_shop: Path) -> None:
    result = run_cli("init")
    warnings = [line for line in result.stderr_json_lines() if line["level"] == "warning"]

    assert (result.exit_code, [(line["code"], line["details"]) for line in warnings]) == (
        0,
        [("workspace_nested", {"parent": str(shop)})],
    )


def test_a_warning_keeps_exit_code_0(blog_in_shop: Path) -> None:
    assert run_cli("init").exit_code == 0


def test_unwritable_target_folder(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "notes.txt").write_bytes(b"")
    site = temp_workspace.root / "notes.txt" / "site"

    result = run_cli("init", "--workspace", str(site))
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], str(site) in error["message"]) == (
        7,
        "workspace_not_writable",
        True,
    )


def test_a_crawls_entry_that_is_a_file_makes_the_workspace_unwritable(shop: Path) -> None:
    (shop / ".spider").mkdir()
    (shop / ".spider" / "crawls").write_bytes(b"")

    result = run_cli("init")

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (
        7,
        "workspace_not_writable",
    )


def test_no_nested_warning_for_a_workspace_above_a_target_outside_home(
    temp_workspace: TempWorkspace,
) -> None:
    outer = temp_workspace.home.parent / "outer"
    (outer / ".spider").mkdir(parents=True)

    result = run_cli("init", "--workspace", str(outer / "site"))

    assert (result.exit_code, result.stderr) == (0, b"")
