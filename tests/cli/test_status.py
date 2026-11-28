"""Read the status of real Crawls through the CLI."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli, run_cli_process
from tests.support.crawls import query, sha256_of
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_status_of_a_completed_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite, journal: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal}"\n', encoding="utf-8"
    )
    site = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<a href="/a">A</a><a href="/b">B</a><a href="/missing">Missing</a>'
                ),
                "/a": Page(body="<title>A</title>"),
                "/b": Page(body="<title>B</title>"),
            }
        )
    )
    started = run_cli("crawl", site.url("/"))
    assert started.exit_code == 0, started.stderr
    crawl = started.json()
    assert crawl["state"] == "completed"
    path = Path(crawl["crawl_file"])
    [(completed_at,)] = query(path, "SELECT completed_at FROM crawl")
    assert completed_at is not None
    fingerprint = sha256_of(path)

    reply = run_cli_process("status", "--crawl", crawl["crawl_id"])

    assert reply.exit_code == 0, reply.stderr
    status = reply.json()
    assert (status["crawl_id"], status["state"], status["stop_reason"]) == (
        crawl["crawl_id"],
        "completed",
        None,
    )
    assert (status["seed"], status["seed_count"], status["completed_at"]) == (
        site.url("/"),
        1,
        completed_at,
    )
    assert status["urls"] == {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0}
    assert status["status_classes"] == {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0}
    assert status["eta_s"] is None
    assert sha256_of(path) == fingerprint


def test_status_defaults_to_the_latest_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    site = fixture_site(
        Site(routes={"/first": Page(body="<p>First</p>"), "/second": Page(body="<p>Second</p>")})
    )
    first = run_cli("crawl", site.url("/first"))
    second = run_cli("crawl", site.url("/second"))
    assert (first.exit_code, second.exit_code) == (0, 0), (first.stderr, second.stderr)
    first_id = first.json()["crawl_id"]
    second_id = second.json()["crawl_id"]
    assert first_id != second_id

    latest = run_cli_process("status")
    explicit_first = run_cli_process("status", "--crawl", first_id)

    assert (latest.exit_code, explicit_first.exit_code) == (0, 0), (
        latest.stderr,
        explicit_first.stderr,
    )
    assert (latest.json()["crawl_id"], latest.json()["seed"]) == (second_id, site.url("/second"))
    assert (explicit_first.json()["crawl_id"], explicit_first.json()["seed"]) == (
        first_id,
        site.url("/first"),
    )


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_status_reports_a_crawl_without_its_seeds_as_invalid(
    temp_workspace: TempWorkspace, fixture_site: StartSite, journal: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal}"\n', encoding="utf-8"
    )
    site = fixture_site(Site(routes={"/": Page(body="<title>Seed</title>")}))
    created = run_cli("crawl", site.url("/"))
    assert created.exit_code == 0, created.stderr
    path = Path(created.json()["crawl_file"])
    healthy = run_cli_process("status", "--crawl", str(path))
    assert healthy.exit_code == 0, healthy.stderr
    assert healthy.json()["seed_count"] == 1

    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP TABLE seeds")
    fingerprint = sha256_of(path)

    reply = run_cli_process("status", "--crawl", str(path))

    assert reply.exit_code == 6, reply.stderr
    assert reply.stdout == b""
    diagnostic = reply.errors()[-1]
    assert (diagnostic["code"], diagnostic["details"]["file"]) == ("crawl_file_invalid", str(path))
    assert sha256_of(path) == fingerprint
