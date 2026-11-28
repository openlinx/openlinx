"""Read Issues through the public Command after crawling a synthetic site."""

import json
from pathlib import Path

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.cli import CRAWL_PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_issues_of_a_fixture_crawl_on_every_os(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    workspace = temp_workspace.root / "fixture workspace"
    workspace_options = ("--workspace", str(workspace))
    initialized = run_cli("init", *workspace_options)
    assert initialized.exit_code == 0, initialized.stderr

    site = fixture_site(
        Site(
            routes={
                "/robots.txt": Robots("User-agent: *\nAllow: /\n"),
                "/e2e/": Page(
                    body="<title>Home</title><h1>Home</h1><h2>Links</h2>"
                    '<a href="/e2e/notitle">Article</a><a href="/e2e/gone">Gone</a>'
                ),
                "/e2e/notitle": Page(body="<h1>Article</h1><h2>Section</h2>"),
                "/e2e/gone": Status(404),
            }
        )
    )
    seed = site.url("/e2e/")
    missing_title = site.url("/e2e/notitle")
    gone = site.url("/e2e/gone")

    crawl = run_cli_process("crawl", seed, *workspace_options, timeout=CRAWL_PROCESS_TIMEOUT)
    assert crawl.exit_code == 0, crawl.stderr
    result = crawl.json()
    assert (result["state"], result["pages"]) == ("completed", 2)
    assert result["urls"] == {"discovered": 3, "fetched": 3, "errors": 0, "skipped": 0, "queued": 0}
    assert result["status_classes"] == {"2xx": 2, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0}
    crawl_file = Path(result["crawl_file"])
    assert crawl_file.resolve().is_relative_to(workspace.resolve())
    assert query(crawl_file, "SELECT url, status_code FROM urls ORDER BY url") == [
        (seed, 200),
        (gone, 404),
        (missing_title, 200),
    ]
    assert query(
        crawl_file, "SELECT address, title_1, title_count FROM pages ORDER BY address"
    ) == [
        (seed, "Home", 1),
        (missing_title, None, 0),
    ]

    listed = run_cli_process("issues", *workspace_options)
    assert listed.exit_code == 0, listed.stderr
    assert [
        (item["rule_id"], item["affected_count"])
        for item in listed.json()["items"]
        if item["rule_id"] in {"internal-4xx", "title-missing"}
    ] == [("internal-4xx", 1), ("title-missing", 1)]

    selection = (*workspace_options, "--crawl", str(crawl_file))
    affected = run_cli_process("issues", "internal-4xx", *selection)
    assert affected.exit_code == 0, affected.stderr
    detail = affected.json()
    assert (detail["rule"]["rule_id"], detail["total"], detail["items"], detail["next_cursor"]) == (
        "internal-4xx",
        1,
        [{"url": gone, "detail": {"status_code": 404}}],
        None,
    )

    title = run_cli_process("issues", "title-missing", *selection, "--format", "jsonl")
    assert title.exit_code == 0, title.stderr
    assert [json.loads(line) for line in title.stdout.splitlines()] == [
        {"url": missing_title, "detail": None}
    ]

    assert sorted((request.method, request.path) for request in site.requests) == [
        ("GET", "/e2e/"),
        ("GET", "/e2e/gone"),
        ("GET", "/e2e/notitle"),
        ("GET", "/robots.txt"),
    ]
