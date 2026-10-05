"""Selecting a Crawl with --crawl (015-add-crawl-store, crawl-store)."""

import pytest

from spider.output.diagnostics import SpiderError
from spider.store.crawls import set_state
from spider.store.records import CrawlFile
from spider.store.selection import resolve_crawl
from spider.store.writer import CrawlWriter
from spider.workspace.discovery import Workspace, resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, create_crawl_at
from tests.support.workspace import TempWorkspace


def current_workspace(temp_workspace: TempWorkspace) -> Workspace:
    return resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)


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


def test_no_crawls(temp_workspace: TempWorkspace) -> None:
    with pytest.raises(SpiderError) as raised:
        resolve_latest(temp_workspace)

    assert (raised.value.code, raised.value.exit_code) == ("no_crawls", 4)


def test_unknown_id(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    workspace = current_workspace(temp_workspace)

    with pytest.raises(SpiderError) as raised:
        resolve_crawl("20260101-000000-zzzz", workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.exit_code) == ("crawl_not_found", 4)


def test_malformed_reference(temp_workspace: TempWorkspace) -> None:
    workspace = current_workspace(temp_workspace)

    with pytest.raises(SpiderError) as raised:
        resolve_crawl("yesterday", workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.exit_code) == ("invalid_value", 2)


def test_not_a_crawl_file(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.root / "notes.sqlite"
    notes.write_text("hello", encoding="utf-8")
    workspace = current_workspace(temp_workspace)

    with pytest.raises(SpiderError) as raised:
        resolve_crawl(str(notes), workspace=workspace, cwd=temp_workspace.root)

    assert (
        raised.value.code,
        raised.value.exit_code,
        raised.value.diagnostic.details["file"],
    ) == ("crawl_file_invalid", 6, str(notes))


def test_a_sqlite_file_not_named_by_an_id_is_not_a_crawl(temp_workspace: TempWorkspace) -> None:
    crawl = create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    (crawl.path.parent / "notes.sqlite").write_text("", encoding="utf-8")

    assert resolve_latest(temp_workspace) == "20260927-100000-aaaa"
