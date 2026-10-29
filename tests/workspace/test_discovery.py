"""Finding the Workspace (010-add-workspace-and-cli-contract, workspace)."""

import sys
from pathlib import Path

import pytest

from openlinx.output.diagnostics import OpenLinxError
from openlinx.workspace.discovery import resolve_workspace
from tests.support.workspace import TempWorkspace


def test_workspace_in_the_current_folder(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / ".openlinx").mkdir(parents=True)

    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_workspace_in_a_parent_folder(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / ".openlinx").mkdir(parents=True)
    (shop / "blog").mkdir()

    workspace = resolve_workspace(cwd=shop / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_the_nearest_workspace_wins(temp_workspace: TempWorkspace) -> None:
    work = temp_workspace.home / "work"
    (work / ".openlinx").mkdir()
    (work / "shop" / ".openlinx").mkdir(parents=True)
    (work / "shop" / "blog").mkdir()

    workspace = resolve_workspace(cwd=work / "shop" / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == work / "shop"


def test_a_settings_file_alone_marks_a_workspace(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.home / "work" / "shop"
    (shop / "blog").mkdir(parents=True)
    (shop / "openlinx.toml").write_text("", encoding="utf-8")

    workspace = resolve_workspace(cwd=shop / "blog", flag=None, home=temp_workspace.home)

    assert workspace.root == shop


def test_fallback_to_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.home / "work" / "notes"
    notes.mkdir(parents=True)

    workspace = resolve_workspace(cwd=notes, flag=None, home=temp_workspace.home)

    assert (workspace.is_global, workspace.data_dir) == (True, temp_workspace.home / ".openlinx")


def test_the_home_folder_is_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    home = temp_workspace.home
    (home / ".openlinx").mkdir()

    workspace = resolve_workspace(cwd=home, flag=None, home=home)

    assert (workspace.is_global, workspace.settings_file) == (
        True,
        home / ".openlinx" / "openlinx.toml",
    )


def test_location_of_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    home = temp_workspace.home

    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=home)

    assert (workspace.data_dir, workspace.settings_file) == (
        home / ".openlinx",
        home / ".openlinx" / "openlinx.toml",
    )


def test_the_flag_wins(temp_workspace: TempWorkspace) -> None:
    work = temp_workspace.home / "work"
    (work / "a" / ".openlinx").mkdir(parents=True)
    (work / "b").mkdir()

    workspace = resolve_workspace(cwd=work / "a", flag=work / "b", home=temp_workspace.home)

    assert workspace.root == work / "b"


def test_the_home_folder_given_with_workspace_is_the_global_workspace(
    temp_workspace: TempWorkspace,
) -> None:
    home = temp_workspace.home
    (home / "work" / "a").mkdir()

    workspace = resolve_workspace(cwd=home / "work" / "a", flag=home, home=home)

    assert (workspace.is_global, workspace.settings_file) == (
        True,
        home / ".openlinx" / "openlinx.toml",
    )


def test_missing_workspace_folder_is_workspace_not_found(temp_workspace: TempWorkspace) -> None:
    home = temp_workspace.home

    with pytest.raises(OpenLinxError) as raised:
        resolve_workspace(cwd=temp_workspace.root, flag=home / "missing", home=home)

    assert (raised.value.code, raised.value.exit_code) == ("workspace_not_found", 4)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths only")
def test_forward_slashes_on_windows(temp_workspace: TempWorkspace) -> None:
    home = temp_workspace.home
    (home / "work" / "b").mkdir()

    workspace = resolve_workspace(
        cwd=temp_workspace.root, flag=Path(home.as_posix() + "/work/b"), home=home
    )

    assert str(workspace.root) == str(home) + r"\work\b"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths only")
def test_home_folder_with_non_ascii_characters_on_windows(tmp_path: Path) -> None:
    home = tmp_path / "Пользователь"
    (home / "notes").mkdir(parents=True)

    workspace = resolve_workspace(cwd=home / "notes", flag=None, home=home)

    assert str(workspace.data_dir) == str(home) + r"\.openlinx"


def test_a_workspace_variable_is_ignored(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = temp_workspace.home / "work"
    (work / "a" / ".openlinx").mkdir(parents=True)
    (work / "b" / ".openlinx").mkdir(parents=True)
    monkeypatch.setenv("OPENLINX_WORKSPACE", str(work / "b"))
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")

    workspace = resolve_workspace(cwd=work / "a", flag=None, home=temp_workspace.home)

    assert workspace.root == work / "a"


def test_the_home_folder_given_with_dot_dot_is_the_global_workspace(
    temp_workspace: TempWorkspace,
) -> None:
    home = temp_workspace.home

    workspace = resolve_workspace(cwd=temp_workspace.root, flag=Path(".."), home=home)

    assert (workspace.is_global, workspace.settings_file) == (
        True,
        home / ".openlinx" / "openlinx.toml",
    )
