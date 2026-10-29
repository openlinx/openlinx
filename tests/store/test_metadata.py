"""Crawl metadata (015-add-crawl-store, crawl-store)."""

import json
import re
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openlinx.output.reporter import Collected
from openlinx.services.crawls import create_crawl
from openlinx.store.crawls import set_state
from openlinx.store.records import NewCrawl, SecretNames
from openlinx.store.writer import CrawlWriter
from openlinx.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, crawl_row, create_any_crawl, new_crawl, query
from tests.support.project import project_version
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace


def test_metadata_of_a_new_crawl(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".openlinx").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    request = NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        seeds=["https://example.com/"],
        command_argv=["linx", "crawl", "https://example.com/"],
        cwd=shop,
        config={"store": {"journal_mode": "auto"}},
        scope={
            "mode": "host",
            "hosts": ["example.com"],
            "folder": None,
            "include": [],
            "exclude": [],
        },
        secret_names=SecretNames(),
        journal_setting="auto",
        section_crawl=False,
    )

    crawl = create_crawl(request, FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9"))

    row = crawl_row(crawl.path)
    decoded = {
        **row,
        "command_argv": json.loads(row["command_argv"]),
        "config": json.loads(row["config"]),
        "warnings": json.loads(row["warnings"]),
    }
    expected = {
        "crawl_mode": "spider",
        "section_crawl": 0,
        "state": "running",
        "started_at": "2026-09-27T14:03:12.345Z",
        "completed_at": None,
        "command_argv": ["linx", "crawl", "https://example.com/"],
        "cwd": str(shop),
        "settings_file": None,
        "config": {"store": {"journal_mode": "auto"}},
        "warnings": [],
    }
    assert {key: decoded[key] for key in expected} == expected


def test_timestamp_text(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    started_at = crawl_row(crawl.path)["started_at"]
    assert (started_at, len(started_at)) == ("2026-09-27T14:03:12.345Z", 24)


def test_seeds_keep_their_order(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(
        temp_workspace, seeds=["https://example.com/b", "https://example.com/a"]
    )

    assert query(crawl.path, "SELECT position, url FROM seeds ORDER BY position") == [
        (1, "https://example.com/b"),
        (2, "https://example.com/a"),
    ]


def test_version_stamp(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    row = crawl_row(crawl.path)
    assert (
        row["tool_version"],
        row["schema_version"],
        query(crawl.path, "PRAGMA user_version"),
    ) == (project_version(), 1, [(1,)])


def test_environment_stamp(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    row = crawl_row(crawl.path)
    python_version, platform = stamp = row["python_version"], row["platform"]
    assert (
        re.fullmatch(r"3\.(12|13|14)\.[0-9]+", python_version) is not None,
        platform != "",
    ) == (True, True), stamp


def test_completion_time(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    completed_at = datetime(2026, 9, 27, 15, 0, 0, tzinfo=UTC)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(lambda connection: set_state(connection, "completed", completed_at))

    assert crawl_row(crawl.path)["completed_at"] == "2026-09-27T15:00:00.000Z"


def test_a_stopped_crawl_has_no_completion_time(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    stopped_at = datetime(2026, 9, 27, 15, 0, 0, tzinfo=UTC)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(lambda connection: set_state(connection, "stopped", stopped_at, "requested"))

    assert crawl_row(crawl.path)["completed_at"] is None


def test_a_running_crawl_has_no_completion_time(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    row = crawl_row(crawl.path)
    assert (row["state"], row["completed_at"]) == ("running", None)


def test_no_settings_file(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    assert crawl_row(crawl.path)["settings_file"] is None


def test_local_disk(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    assert (
        crawl_row(crawl.path)["journal_mode"],
        query(crawl.path, "PRAGMA journal_mode"),
    ) == ("wal", [("wal",)])


@pytest.mark.skipif(sys.platform != "win32", reason="the admin share is a Windows UNC path")
def test_crawl_on_a_unc_path_on_windows(temp_workspace: TempWorkspace) -> None:
    root = temp_workspace.root
    unc_root = Path(rf"\\localhost\{root.drive[0]}$") / root.relative_to(root.anchor)
    if not unc_root.is_dir():
        pytest.skip(f"the admin share {unc_root.anchor} is not reachable")
    workspace = resolve_workspace(cwd=unc_root, flag=Path(), home=temp_workspace.home)
    reporter = Collected()
    request = replace(new_crawl(workspace), cwd=unc_root)

    crawl = create_crawl(request, FakeClock(start=STARTED_AT), reporter)

    assert (
        crawl_row(crawl.path)["journal_mode"],
        [(warning.code, warning.details["path"]) for warning in reporter.warnings],
    ) == ("delete", [("store_wal_unavailable", str(workspace.data_dir))])
