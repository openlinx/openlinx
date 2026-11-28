"""Check the stop Command's public output and wait option."""

import sqlite3
from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawls import create_any_crawl, query, sha256_of
from tests.support.workspace import TempWorkspace


def test_stop_describes_its_wait_option() -> None:
    [stop] = [entry for entry in run_cli("commands").json()["commands"] if entry["name"] == "stop"]
    [wait] = [option for option in stop["options"] if option["name"] == "--wait"]

    assert (wait["type"], wait["default"], wait["min"], wait["required"], wait["setting"]) == (
        "integer",
        60,
        0,
        False,
        None,
    )


@pytest.mark.parametrize("wait", ["-1", "never"])
def test_invalid_stop_wait_does_not_record_a_request(
    temp_workspace: TempWorkspace, wait: str
) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = run_cli("stop", "--crawl", crawl.id, f"--wait={wait}")

    [error] = result.errors()
    assert (result.exit_code, error["code"], "--wait" in error["message"]) == (
        2,
        "invalid_value",
        True,
    )
    assert query(crawl.path, "SELECT kind FROM control_requests") == []


@pytest.mark.parametrize("journal", ["wal", "delete"])
@pytest.mark.parametrize("link", [None, "original", "alias"], ids=["single", "original", "alias"])
def test_stopping_a_completed_crawl_changes_nothing(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    journal: str,
    link: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal}"\n', encoding="utf-8"
    )
    site = fixture_site(Site(routes={"/": Page(body="<title>Index</title>")}))
    finished = run_cli("crawl", site.url("/"))
    assert finished.exit_code == 0, finished.stderr
    crawl = finished.json()
    assert crawl["state"] == "completed"
    file = Path(crawl["crawl_file"])
    assert query(file, "PRAGMA journal_mode") == [(journal,)]
    assert query(file, "SELECT title_1 FROM pages") == [("Index",)]
    assert query(file, "SELECT id FROM control_requests") == []
    fingerprint = sha256_of(file)
    reference = crawl["crawl_id"]
    if link is not None:
        alias = file.with_name("alias.sqlite")
        alias.hardlink_to(file)
        assert alias.samefile(file)
        assert file.stat().st_nlink == 2
        reference = str(alias if link == "alias" else file)

    connect = sqlite3.connect
    writable_opens: list[str] = []

    def observe_connect(database: str, *, uri: bool, timeout: float) -> sqlite3.Connection:
        if database.endswith("?mode=rw"):
            writable_opens.append(database)
        return connect(database, uri=uri, timeout=timeout)

    for wait in ((), ("--wait", "0")):
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", observe_connect)
            result = run_cli("stop", "--crawl", reference, *wait)
        assert result.exit_code == 0, result.stderr
        assert result.json() == {
            "crawl_id": crawl["crawl_id"],
            "state": "completed",
            "stop_reason": None,
            "stop_requested": False,
        }
        assert writable_opens == []
        assert query(file, "SELECT id FROM control_requests") == []
        assert sha256_of(file) == fingerprint
