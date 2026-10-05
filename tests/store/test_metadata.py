"""Crawl metadata (015-add-crawl-store, crawl-store)."""

import json
from datetime import UTC, datetime

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.store.records import NewCrawl
from spider.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_row, new_crawl
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace

STARTED_AT = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)


def test_metadata_of_a_new_crawl(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    request = NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        command_argv=["spider", "crawl", "https://example.com/"],
        cwd=shop,
        config={"store": {"journal_mode": "auto"}},
    )

    crawl = create_crawl(request, FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9"))

    row = crawl_row(crawl.path)
    decoded = {
        **row,
        "command_argv": json.loads(row["command_argv"]),
        "config": json.loads(row["config"]),
    }
    expected = {
        "crawl_mode": "spider",
        "section_crawl": 0,
        "state": "running",
        "started_at": "2026-09-27T14:03:12.345Z",
        "completed_at": None,
        "command_argv": ["spider", "crawl", "https://example.com/"],
        "cwd": str(shop),
        "settings_file": None,
        "config": {"store": {"journal_mode": "auto"}},
    }
    assert {key: decoded[key] for key in expected} == expected


def test_timestamp_text(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    crawl = create_crawl(new_crawl(workspace), FakeClock(start=STARTED_AT), Collected())

    started_at = crawl_row(crawl.path)["started_at"]
    assert (started_at, len(started_at)) == ("2026-09-27T14:03:12.345Z", 24)
