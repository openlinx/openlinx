"""Read the Rule configuration a Crawl leaves in its public schema."""

import json

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawled
from tests.support.crawls import query
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

    rows = query(
        crawled(server.url("/")),
        "SELECT id, category, issue_type, priority, applies_to, enabled, thresholds FROM rules"
        " ORDER BY id",
    )
    catalogue = run_cli("rules", "list", "--limit", "50")

    assert catalogue.exit_code == 0
    assert {row[0] for row in rows} == {item["id"] for item in catalogue.json()["items"]}
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
