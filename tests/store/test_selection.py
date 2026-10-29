"""Selecting a Crawl with --crawl (015-add-crawl-store, crawl-store)."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import delete, update

from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.crawls import set_state
from openlinx.store.records import CrawlFile
from openlinx.store.schema import crawl as crawl_table
from openlinx.store.selection import resolve_crawl
from openlinx.store.writer import CrawlWriter
from openlinx.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, create_crawl_at, current_workspace
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


def test_by_id(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    create_crawl_at(temp_workspace, "2026-09-27T11:00:00.000Z", "bbbb")
    workspace = current_workspace(temp_workspace)

    selected = resolve_crawl("20260927-100000-aaaa", workspace=workspace, cwd=temp_workspace.root)

    assert selected == CrawlFile(
        "20260927-100000-aaaa", workspace.crawls_dir / "20260927-100000-aaaa.sqlite"
    )


def resolve_latest(temp_workspace: TempWorkspace) -> str:
    workspace = current_workspace(temp_workspace)
    return resolve_crawl("latest", workspace=workspace, cwd=temp_workspace.root).id


def test_latest_is_the_most_recent_start(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T11:00:00.000Z", "bbbb")
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")

    assert resolve_latest(temp_workspace) == "20260927-110000-bbbb"


def test_a_running_crawl_can_be_latest(temp_workspace: TempWorkspace) -> None:
    completed = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    with CrawlWriter(completed.path, FakeClock()) as writer:
        writer.run(lambda connection: set_state(connection, "completed", STARTED_AT))
    create_crawl_at(temp_workspace, "2026-09-27T11:00:00.000Z", "bbbb")

    assert resolve_latest(temp_workspace) == "20260927-110000-bbbb"


def test_two_crawls_in_the_same_second(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.100Z", "zzzz")
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.900Z", "aaaa")

    assert resolve_latest(temp_workspace) == "20260927-100000-aaaa"


def test_only_crawl_files_are_crawls(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    (crawl.path.parent / "20260927-110000-bbbb.log").write_text("", encoding="utf-8")

    assert resolve_latest(temp_workspace) == "20260927-100000-aaaa"


def test_companion_files_are_not_crawls(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    (crawl.path.parent / "20260927-110000-bbbb.sqlite-wal").write_bytes(b"")

    assert resolve_latest(temp_workspace) == "20260927-100000-aaaa"


def test_no_crawls(temp_workspace: TempWorkspace) -> None:
    with pytest.raises(OpenLinxError) as raised:
        resolve_latest(temp_workspace)

    assert (raised.value.code, raised.value.exit_code) == ("no_crawls", 4)


def test_unknown_id(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    workspace = current_workspace(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        resolve_crawl("20260101-000000-zzzz", workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.exit_code) == ("crawl_not_found", 4)


def test_malformed_reference(temp_workspace: TempWorkspace) -> None:
    workspace = current_workspace(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        resolve_crawl("yesterday", workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.exit_code) == ("invalid_value", 2)


def test_not_a_crawl_file(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.root / "notes.sqlite"
    notes.write_text("hello", encoding="utf-8")
    workspace = current_workspace(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        resolve_crawl(str(notes), workspace=workspace, cwd=temp_workspace.root)

    assert (
        raised.value.code,
        raised.value.exit_code,
        raised.value.diagnostic.details["file"],
    ) == ("crawl_file_invalid", 6, str(notes))


def test_a_crawl_file_without_its_crawl_row(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(executing(delete(crawl_table)))

    with pytest.raises(OpenLinxError) as raised:
        resolve_latest(temp_workspace)

    assert raised.value.code == "crawl_file_invalid"


def test_a_missing_crawl_file_path(temp_workspace: TempWorkspace) -> None:
    missing = temp_workspace.root / "none.sqlite"
    workspace = current_workspace(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        resolve_crawl("none.sqlite", workspace=workspace, cwd=temp_workspace.root)

    assert (
        raised.value.code,
        raised.value.exit_code,
        raised.value.diagnostic.details["file"],
    ) == ("crawl_not_found", 4, str(missing))


def test_a_crawl_file_that_holds_another_id(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(executing(update(crawl_table).values(id="20260927-090000-zzzz")))
    workspace = current_workspace(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        resolve_crawl("20260927-100000-aaaa", workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.diagnostic.details) == (
        "crawl_file_invalid",
        {
            "file": str(crawl.path),
            "expected_id": "20260927-100000-aaaa",
            "found_id": "20260927-090000-zzzz",
        },
    )


def holding_another_id(crawl: CrawlFile, crawl_id: str) -> None:
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(executing(update(crawl_table).values(id=crawl_id)))


def test_latest_that_holds_another_id(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    newest = create_crawl_at(temp_workspace, "2026-09-27T11:00:00.000Z", "bbbb")
    holding_another_id(newest, "20260927-090000-zzzz")

    with pytest.raises(OpenLinxError) as raised:
        resolve_latest(temp_workspace)

    assert (raised.value.code, raised.value.diagnostic.details["expected_id"]) == (
        "crawl_file_invalid",
        "20260927-110000-bbbb",
    )


def test_a_same_second_file_that_holds_another_id_is_reported(
    temp_workspace: TempWorkspace,
) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.900Z", "aaaa")
    loser = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.100Z", "zzzz")
    holding_another_id(loser, "20260927-090000-yyyy")

    with pytest.raises(OpenLinxError) as raised:
        resolve_latest(temp_workspace)

    assert raised.value.diagnostic.details["file"] == str(loser.path)


def test_a_renamed_file_opens_by_its_path_with_the_id_it_holds(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    copy = temp_workspace.root / "c.sqlite"
    shutil.copyfile(crawl.path, copy)
    workspace = current_workspace(temp_workspace)

    selected = resolve_crawl(str(copy), workspace=workspace, cwd=temp_workspace.root)

    assert selected == CrawlFile("20260927-100000-aaaa", copy)


def test_a_broken_newest_file_is_reported_not_skipped(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    (crawl.path.parent / "20260927-110000-bbbb.sqlite").write_bytes(b"")

    with pytest.raises(OpenLinxError) as raised:
        resolve_latest(temp_workspace)

    assert (raised.value.code, Path(raised.value.diagnostic.details["file"]).name) == (
        "crawl_file_invalid",
        "20260927-110000-bbbb.sqlite",
    )


def test_reading_creates_nothing(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.root / "notes"
    notes.mkdir()
    workspace = resolve_workspace(cwd=notes, flag=None, home=temp_workspace.home)

    with pytest.raises(OpenLinxError):
        resolve_crawl("latest", workspace=workspace, cwd=notes)

    assert (workspace.is_global, (temp_workspace.home / ".openlinx").exists()) == (True, False)


def test_a_sqlite_file_not_named_by_an_id_is_not_a_crawl(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    (crawl.path.parent / "notes.sqlite").write_text("", encoding="utf-8")

    assert resolve_latest(temp_workspace) == "20260927-100000-aaaa"
