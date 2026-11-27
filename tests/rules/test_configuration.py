"""Read the Rule configuration a Crawl leaves in its public schema."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from openlinx.services.crawling import CrawlOverrides
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import continued, crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.rules import V01_RULE_IDS
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
    assert len(rows) == 15
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
    assert recorded["title-too-long"] == {"enabled": True, "max_chars": 70}
    assert {rule_id for (rule_id,) in query(file, "SELECT id FROM rules")} == V01_RULE_IDS


def test_continue_preserves_the_preview_snapshot_and_applies_an_active_rule(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/next">Next</a>'),
                "/next": Page(body=f"<title>{'a' * 71}</title>"),
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
    file = stopped.crawl_file
    _add_preview_rule_snapshot(file)
    recorded = json.loads(crawl_row(file)["config"])["rules"]
    rules = query(file, "SELECT * FROM rules ORDER BY id")
    assert recorded.keys() == V01_RULE_IDS | {"h2-missing", "low-word-count", "url-parameters"}
    assert len(rules) == 18

    settings_file.write_bytes(b"[rules.title-too-long]\nmax_chars = 90\n")
    result = continued(stopped, CrawlOverrides(max_urls=None))

    assert result.summary.state == "completed"
    assert [(request.method, request.path) for request in server.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/"),
        ("GET", "/robots.txt"),
        ("GET", "/next"),
    ]
    assert json.loads(crawl_row(file)["config"])["rules"] == recorded
    assert query(file, "SELECT * FROM rules ORDER BY id") == rules
    [(url, detail)] = query(
        file,
        "SELECT urls.url, a.detail FROM affected_urls AS a JOIN urls ON urls.id = a.url_id"
        " WHERE a.rule_id = 'title-too-long'",
    )
    assert (url, json.loads(detail)) == (server.url("/next"), {"length": 71})


def _add_preview_rule_snapshot(file: Path) -> None:
    config = json.loads(crawl_row(file)["config"])
    with closing(sqlite3.connect(file)) as connection, connection:
        for rule_id, category, priority, thresholds in (
            ("h2-missing", "headings", "low", {}),
            ("low-word-count", "content", "medium", {"min_words": 200}),
            ("url-parameters", "urls", "low", {}),
        ):
            config["rules"][rule_id] = {"enabled": True, **thresholds}
            connection.execute(
                """INSERT OR IGNORE INTO rules (
                    id, category, issue_type, priority, applies_to, enabled, thresholds,
                    description, why_it_matters, how_to_fix, reproduce_sql
                ) VALUES (?, ?, 'opportunity', ?, 'internal_pages',"""
                " 1, ?, 'Preview Rule', 'Preview guidance', 'Preview fix',"
                " 'SELECT id AS url_id, NULL AS detail FROM urls WHERE 0')",
                (rule_id, category, priority, json.dumps(thresholds)),
            )
        connection.execute("UPDATE crawl SET config = ?", (json.dumps(config),))
