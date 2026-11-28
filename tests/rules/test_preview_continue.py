"""Exercise Continue over Crawl files made by the shipped Rules preview."""

import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from openlinx.clock import SystemClock
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides, continue_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.reading import read_metadata
from openlinx.store.records import CrawlFile
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
from tests.support.cli import run_cli
from tests.support.crawls import crawl_row, query
from tests.support.rules import PREVIEW_LIVE_RULE_IDS, PREVIEW_NO_ROWS, PREVIEW_RULE_IDS
from tests.support.workspace import TempWorkspace

_FIXTURES = Path(__file__).with_name("fixtures")
_NEXT = "/guide?p=1"
_SCHEMA = "SELECT type, name, sql FROM sqlite_schema ORDER BY type, name"
_RULES = "SELECT * FROM rules ORDER BY id"


def _preview_copy(
    workspace: TempWorkspace, fixture_site: StartSite, journal: str
) -> tuple[CrawlFile, ServerHandle]:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Index</title><a href="/guide?p=1">Guide</a>'),
                "/guide": Page(body=f"<title>{'X' * 71}</title><main>one two</main>"),
            }
        )
    )
    file = workspace.root / "preview.sqlite"
    file.write_bytes(gzip.decompress((_FIXTURES / f"preview-{journal}.sqlite.gz").read_bytes()))
    # Rebind only the loopback port to the fixture server on this run.
    with closing(sqlite3.connect(file)) as db, db:
        [(seed,)] = db.execute("SELECT url FROM seeds").fetchall()
        target = server.base_url
        db.execute("UPDATE seeds SET url = ?", (target,))
        db.execute("UPDATE urls SET url = replace(url, ?, ?)", (seed, target))
    (workspace.root / "openlinx.toml").write_text(
        "[rules.title-too-long]\nmax_chars = 90\n", encoding="utf-8"
    )
    return CrawlFile(crawl_row(file)["id"], file), server


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_continuing_a_historical_preview_leaves_stored_health_unavailable(
    temp_workspace: TempWorkspace, fixture_site: StartSite, journal: str
) -> None:
    selected, server = _preview_copy(temp_workspace, fixture_site, journal)
    file = selected.path
    row = crawl_row(file)
    config = json.loads(row["config"])["rules"]
    schema = query(file, _SCHEMA)
    rules = query(file, _RULES)
    assert row["state"] == "stopped"
    assert query(file, "PRAGMA journal_mode") == [(journal,)]
    assert not any(name.startswith("health_") for name in row)
    assert config.keys() == PREVIEW_LIVE_RULE_IDS | PREVIEW_RULE_IDS
    assert config["title-too-long"]["max_chars"] == 70
    initial_requests = server.requests
    assert initial_requests == ()

    resumed = continue_crawl(
        selected, CrawlOverrides(max_urls=2), SystemClock(), Collected(), default_hooks()
    )

    assert (resumed.summary.state, resumed.failure, resumed.crawl_file) == ("completed", None, file)
    assert [request.path for request in server.requests] == ["/robots.txt", _NEXT]
    assert query(file, "SELECT title_1 FROM pages ORDER BY url_id") == [("Index",), ("X" * 71,)]
    assert query(file, _SCHEMA) == schema
    assert query(file, "PRAGMA journal_mode") == [(journal,)]
    assert query(file, _RULES) == rules
    assert json.loads(crawl_row(file)["config"])["rules"] == config
    assert not any(name.startswith("health_") for name in read_metadata(file))

    shown = run_cli("issues", "title-too-long", "--crawl", str(file))
    assert shown.exit_code == 0, shown.stderr
    assert shown.json()["items"] == [{"url": server.url(_NEXT), "detail": {"length": 71}}]
    for rule_id in sorted(PREVIEW_RULE_IDS):
        shown = run_cli("issues", rule_id, "--crawl", str(file))
        assert shown.exit_code == 0, shown.stderr
        issue = shown.json()
        assert (issue["total"], issue["items"], issue["rule"]["reproduce_sql"]) == (
            0,
            [],
            PREVIEW_NO_ROWS,
        )


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(
            "UPDATE rules SET reproduce_sql = reproduce_sql || ' ' WHERE id = 'h2-missing'",
            id="one-placeholder-differs",
        ),
        pytest.param(
            "UPDATE crawl SET config = json_remove(config, '$.rules.\"noindex\"')",
            id="one-config-entry-missing",
        ),
        pytest.param("ALTER TABLE pages ADD COLUMN unexpected TEXT", id="other-layout"),
        pytest.param("ALTER TABLE crawl ADD COLUMN health_score INTEGER", id="partial-health"),
    ],
)
def test_continue_refuses_an_unrecognised_preview_before_writing(
    temp_workspace: TempWorkspace, fixture_site: StartSite, change: str
) -> None:
    selected, server = _preview_copy(temp_workspace, fixture_site, "delete")
    with closing(sqlite3.connect(selected.path)) as db, db:
        db.execute(change)
        before = tuple(db.iterdump())
    reporter = Collected()

    with pytest.raises(OpenLinxError) as caught:
        continue_crawl(
            selected, CrawlOverrides(max_urls=2), SystemClock(), reporter, default_hooks()
        )

    assert caught.value.code == "crawl_file_invalid"
    assert reporter.events == []
    assert server.requests == ()
    with closing(sqlite3.connect(selected.path)) as db:
        assert tuple(db.iterdump()) == before
