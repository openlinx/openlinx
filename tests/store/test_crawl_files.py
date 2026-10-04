"""Crawl files in the Workspace (015-add-crawl-store, crawl-store)."""

from spider.store.crawls import create_crawl
from spider.workspace.discovery import resolve_workspace
from tests.support.workspace import TempWorkspace


def test_location_of_a_crawl_file(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider" / "crawls").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    create_crawl(workspace, crawl_id="20260927-140312-k3f9")

    assert (shop / ".spider" / "crawls" / "20260927-140312-k3f9.sqlite").is_file()


def test_first_crawl_in_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    create_crawl(workspace, crawl_id="20260927-140312-k3f9")

    assert (temp_workspace.home / ".spider" / "crawls" / "20260927-140312-k3f9.sqlite").is_file()
