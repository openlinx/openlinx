"""Crawl files in the Workspace (015-add-crawl-store, crawl-store)."""

from datetime import UTC, datetime

import pytest

from spider.output.diagnostics import SpiderError
from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, new_crawl
from tests.support.permissions import unwritable_folder
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace


def test_location_of_a_crawl_file(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider" / "crawls").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    )

    assert (shop / ".spider" / "crawls" / "20260927-140312-k3f9.sqlite").is_file()


def test_first_crawl_in_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    )

    data = temp_workspace.home / ".spider"
    assert (
        (data / "crawls" / "20260927-140312-k3f9.sqlite").is_file(),
        (data / ".gitignore").is_file(),
    ) == (
        True,
        True,
    )


def test_no_settings_file_is_created_by_storing_a_crawl(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    )

    assert not (shop / "spider.toml").exists()


def test_unwritable_data_folder(temp_workspace: TempWorkspace) -> None:
    data = temp_workspace.home / ".spider"
    data.write_text("not a folder", encoding="utf-8")
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    with pytest.raises(SpiderError) as raised:
        create_crawl(new_crawl(workspace), FakeClock(), Collected())

    assert (raised.value.code, raised.value.diagnostic.details["path"].startswith(str(data))) == (
        "workspace_not_writable",
        True,
    )


def test_a_taken_id_is_drawn_again(temp_workspace: TempWorkspace) -> None:
    crawls = temp_workspace.home / ".spider" / "crawls"
    crawls.mkdir(parents=True)
    (crawls / "20260927-140312-k3f9.sqlite").touch()
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    clock = FakeClock(start=datetime(2026, 9, 27, 14, 3, 12, 900000, tzinfo=UTC))

    crawl = create_crawl(new_crawl(workspace), clock, Collected(), scripted_choice("k3f9m2p7"))

    assert crawl.id == "20260927-140312-m2p7"


def test_unwritable_crawls_folder(temp_workspace: TempWorkspace) -> None:
    crawls = temp_workspace.root / "shop" / ".spider" / "crawls"
    crawls.mkdir(parents=True)
    workspace = resolve_workspace(cwd=crawls.parent.parent, flag=None, home=temp_workspace.home)

    with unwritable_folder(crawls), pytest.raises(SpiderError) as raised:
        create_crawl(new_crawl(workspace), FakeClock(), Collected())

    assert (raised.value.code, raised.value.diagnostic.details["path"].startswith(str(crawls))) == (
        "workspace_not_writable",
        True,
    )
