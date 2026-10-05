"""Selecting a Crawl with --crawl (015-add-crawl-store, crawl-store)."""

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
