"""Read the Rule configuration a Crawl leaves in its public schema."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.rules.headings import H2_MISSING
from openlinx.rules.registry import RULES
from openlinx.services.crawling import CrawlOverrides, CrawlResult
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import read_affected_urls
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
from tests.support.cli import run_cli
from tests.support.crawling import continued, crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.rule_results import assert_rule_results
from tests.support.rules import (
    PREVIEW_LIVE_RULE_IDS,
    PREVIEW_NO_ROWS,
    PREVIEW_RULE_IDS,
    V01_RULE_IDS,
)
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site({"/": Page(body="<title>Home</title>")})


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        pytest.param("70", 70, id="workspace-override"),
        pytest.param("0", 0, id="zero-threshold"),
        pytest.param("9" * 4300, 10**4300 - 1, id="4300-digit-threshold"),
    ],
)
def test_crawl_records_the_thresholds_it_used(
    temp_workspace: TempWorkspace, fixture_site: StartSite, setting: str, expected: int
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "openlinx.toml").write_text(
        f"[rules.title-too-long]\nmax_chars = {setting}\n", encoding="utf-8"
    )

    [(thresholds,)] = query(
        crawled(server.url("/")), "SELECT thresholds FROM rules WHERE id = 'title-too-long'"
    )

    snapshot = json.loads(thresholds)
    assert snapshot == {"max_chars": expected}
    assert type(snapshot["max_chars"]) is int


def test_the_rule_snapshot_keeps_defaults_and_disabled_rules(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-missing]\nenabled = false\n")

    file = crawled(server.url("/"))
    rows = query(
        file,
        "SELECT id, category, issue_type, priority, applies_to, enabled, thresholds FROM rules"
        " ORDER BY id",
    )
    catalogue = run_cli("rules", "list", "--limit", "50")

    assert catalogue.exit_code == 0
    assert {row[0] for row in rows} == {item["id"] for item in catalogue.json()["items"]}
    assert len(rows) == 42
    assert {row[0] for row in rows} == V01_RULE_IDS
    assert json.loads(crawl_row(file)["config"])["rules"].keys() == V01_RULE_IDS
    assert [
        (rule_id, *metadata, json.loads(thresholds))
        for rule_id, *metadata, thresholds in rows
        if rule_id in {"title-missing", "title-too-long"}
    ] == [
        ("title-missing", "titles", "issue", "high", "internal_pages", 0, {}),
        (
            "title-too-long",
            "titles",
            "opportunity",
            "medium",
            "internal_pages",
            1,
            {"max_chars": 60},
        ),
    ]


def test_empty_preview_rule_tables_are_accepted_without_rewriting(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    settings_file = temp_workspace.root / "openlinx.toml"
    original = (
        b"[rules.h2-missing]\n# enabled = true\n\n"
        b"[rules.low-word-count]\n# min_words = 200\n# enabled = true\n\n"
        b"[rules.url-parameters]\n# enabled = true\n\n"
        b"[rules.title-too-long]\nmax_chars = 70\n"
    )
    settings_file.write_bytes(original)

    initialized = run_cli("init")
    assert initialized.exit_code == 0, initialized.stderr
    shown = run_cli("rules", "show", "title-too-long")
    assert shown.exit_code == 0, shown.stderr
    assert shown.json()["thresholds"]["max_chars"]["value"] == 70
    file = crawled(server.url("/"))
    assert [(request.method, request.path) for request in server.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/"),
    ]
    assert settings_file.read_bytes() == original
    recorded = json.loads(crawl_row(file)["config"])["rules"]
    assert recorded.keys() == V01_RULE_IDS
    assert {rule_id: recorded[rule_id] for rule_id in PREVIEW_RULE_IDS} == {
        "h2-missing": {"enabled": True},
        "low-word-count": {"enabled": True, "min_words": 200},
        "url-parameters": {"enabled": True},
    }
    assert recorded["title-too-long"] == {"enabled": True, "max_chars": 70}
    assert {rule_id for (rule_id,) in query(file, "SELECT id FROM rules")} == V01_RULE_IDS


@pytest.fixture
def explicit_preview_settings_crawl(temp_workspace: TempWorkspace, fixture_site: StartSite) -> Path:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "openlinx.toml").write_text(
        "[rules.h2-missing]\nenabled = false\n\n[rules.low-word-count]\nmin_words = 300\n",
        encoding="utf-8",
    )
    result = crawl_result(server.url("/"))
    assert result.summary.state == "completed"
    return result.crawl_file


def test_explicit_settings_for_formerly_preview_rules(
    explicit_preview_settings_crawl: Path,
) -> None:
    file = explicit_preview_settings_crawl
    recorded = json.loads(crawl_row(file)["config"])["rules"]
    assert recorded["h2-missing"] == {"enabled": False}
    assert recorded["low-word-count"] == {"enabled": True, "min_words": 300}
    assert query(file, "SELECT enabled FROM rules WHERE id = 'h2-missing'") == [(0,)]


def test_crawl_records_the_word_count_threshold(explicit_preview_settings_crawl: Path) -> None:
    [(thresholds,)] = query(
        explicit_preview_settings_crawl,
        "SELECT thresholds FROM rules WHERE id = 'low-word-count'",
    )
    assert json.loads(thresholds) == {"min_words": 300}


@pytest.fixture
def stopped_preview_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> tuple[CrawlResult, ServerHandle]:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/next?page=2">Next</a>'),
                "/next": Page(body=f"<title>{'a' * 71}</title><p>Two words</p>"),
            }
        )
    )
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    assert [(request.method, request.path) for request in server.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/"),
    ]
    _restore_preview_rule_snapshot(stopped.crawl_file)
    return stopped, server


def test_continue_preserves_a_preview_placeholder(
    stopped_preview_crawl: tuple[CrawlResult, ServerHandle],
) -> None:
    stopped, server = stopped_preview_crawl
    file = stopped.crawl_file
    next_url = server.url("/next?page=2")
    live_visits: list[str] = []

    async def observe_live_h2(context: PassContext) -> None:
        await context.writer.flush_async()
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        [(url_id, parsed, h2_count)] = query(
            file,
            "SELECT urls.id, urls.parsed, pages.h2_count FROM urls "
            "JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
            (next_url,),
        )
        assert (parsed, h2_count) == (1, 0)
        assert (url_id, None) in query(file, H2_MISSING.reproduce_sql)
        assert read_affected_urls(file, "h2-missing", RULES) == []
        live_visits.append(next_url)

    defaults = default_hooks()
    hooks = replace(
        defaults, passes=(Pass("observe-preview-h2", observe_live_h2), *defaults.passes)
    )
    result = continued(stopped, CrawlOverrides(max_urls=None), hooks)

    assert result.summary.state == "completed"
    assert result.crawl_file == file
    assert live_visits == [next_url]
    assert query(file, "SELECT reproduce_sql FROM rules WHERE id = 'h2-missing'") == [
        (PREVIEW_NO_ROWS,)
    ]
    assert_rule_results(file, "h2-missing", [])
    assert read_affected_urls(file, "h2-missing", RULES) == []


def test_continue_preserves_the_preview_snapshot_and_applies_an_active_rule(
    temp_workspace: TempWorkspace, stopped_preview_crawl: tuple[CrawlResult, ServerHandle]
) -> None:
    stopped, server = stopped_preview_crawl
    file = stopped.crawl_file
    recorded = json.loads(crawl_row(file)["config"])["rules"]
    rules = query(file, "SELECT * FROM rules ORDER BY id")
    assert recorded.keys() == PREVIEW_LIVE_RULE_IDS | PREVIEW_RULE_IDS
    assert len(rules) == 18

    (temp_workspace.root / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 90\n")
    result = continued(stopped, CrawlOverrides(max_urls=None))

    assert result.summary.state == "completed"
    assert [(request.method, request.path) for request in server.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/"),
        ("GET", "/robots.txt"),
        ("GET", "/next?page=2"),
    ]
    assert json.loads(crawl_row(file)["config"])["rules"] == recorded
    assert query(file, "SELECT * FROM rules ORDER BY id") == rules
    next_url = server.url("/next?page=2")
    expected = [(next_url, {"length": 71})]
    assert _results_for_rule(file, "title-too-long") == expected
    for rule_id in sorted(PREVIEW_RULE_IDS | {"title-too-long"}):
        [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,))
        stored = query(
            file, "SELECT url_id, detail FROM affected_urls WHERE rule_id = ?", (rule_id,)
        )
        assert query(file, sql) == stored
        if rule_id in PREVIEW_RULE_IDS:
            assert sql == PREVIEW_NO_ROWS
            assert stored == []
            shown = run_cli("issues", rule_id, "--crawl", str(file))
            assert shown.exit_code == 0, shown.stderr
            issue = shown.json()
            assert (issue["total"], issue["items"], issue["rule"]["reproduce_sql"]) == (
                0,
                [],
                PREVIEW_NO_ROWS,
            )

    fresh = crawled(next_url)
    for rule_id, detail in (
        ("h2-missing", None),
        ("low-word-count", {"word_count": 2}),
        ("url-parameters", None),
    ):
        assert _results_for_rule(fresh, rule_id) == [(next_url, detail)]


def _results_for_rule(file: Path, rule_id: str) -> list[tuple[str, dict[str, int] | None]]:
    return [
        (url, None if detail is None else json.loads(detail))
        for url, detail in query(
            file,
            "SELECT urls.url, a.detail FROM affected_urls AS a JOIN urls ON urls.id = a.url_id"
            " WHERE a.rule_id = ? ORDER BY a.url_id",
            (rule_id,),
        )
    ]


def _restore_preview_rule_snapshot(file: Path) -> None:
    config = json.loads(crawl_row(file)["config"])
    with closing(sqlite3.connect(file)) as connection, connection:
        removed = [(rule_id,) for rule_id in config["rules"].keys() - PREVIEW_LIVE_RULE_IDS]
        connection.executemany("DELETE FROM affected_urls WHERE rule_id = ?", removed)
        connection.executemany("DELETE FROM rules WHERE id = ?", removed)
        for (rule_id,) in removed:
            del config["rules"][rule_id]
        for rule_id, category, priority, thresholds in (
            ("h2-missing", "headings", "low", {}),
            ("low-word-count", "content", "medium", {"min_words": 200}),
            ("url-parameters", "urls", "low", {}),
        ):
            config["rules"][rule_id] = {"enabled": True, **thresholds}
            connection.execute(
                """INSERT INTO rules (
                    id, category, issue_type, priority, applies_to, enabled, thresholds,
                    description, why_it_matters, how_to_fix, reproduce_sql
                ) VALUES (?, ?, 'opportunity', ?, 'internal_pages',
                          1, ?, 'Preview Rule', 'Preview guidance', 'Preview fix', ?)""",
                (rule_id, category, priority, json.dumps(thresholds), PREVIEW_NO_ROWS),
            )
        connection.execute("UPDATE crawl SET config = ?", (json.dumps(config),))
