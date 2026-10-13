"""`spider crawl` (020-add-crawl-core, crawling)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace

SMALL_SITE = Site(
    routes={
        "/": Page(body='<a href="/a">A</a> <a href="/b">B</a> <a href="/missing">Gone</a>'),
        "/a": Page(body="<p>A</p>"),
        "/b": Page(body="<p>B</p>"),
    }
)


def test_an_invalid_seed_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://exa mple.test/")
    errors = [line["code"] for line in result.stderr_json_lines() if line.get("level") == "error"]

    assert (result.exit_code, errors, list(temp_workspace.home.rglob("*.sqlite"))) == (
        2,
        ["invalid_url"],
        [],
    )


def test_a_seed_with_userinfo_is_rejected_with_a_hint_about_auth(
    temp_workspace: TempWorkspace,
) -> None:
    error = run_cli("crawl", "https://alice:s3cret@site.test/").stderr_json_lines()[-1]

    assert (error["code"], "--auth" in error["hint"], "s3cret" in error["message"]) == (
        "invalid_url",
        True,
        False,
    )


def test_the_ways_a_url_is_found_are_an_enumeration() -> None:
    columns = run_cli("schema", "urls").json()["items"][0]["columns"]
    values = next(column["values"] for column in columns if column["name"] == "discovered_via")

    assert values == [
        "seed",
        "hyperlink",
        "canonical",
        "pagination",
        "hreflang",
        "iframe",
        "meta_refresh",
        "http_refresh",
        "image",
        "css",
        "javascript",
        "video",
        "audio",
        "media",
        "amphtml",
        "mobile_alternate",
        "misc",
        "xml_sitemap",
        "sitemap_hreflang",
        "javascript_redirect",
        "redirect",
        "list",
        "sitemap_input",
        "sitemap_index",
    ]


def test_indexes_of_urls() -> None:
    indexes = run_cli("schema", "urls", "--fields", "indexes").json()["items"][0]["indexes"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")} for index in indexes
    ]

    assert [
        expected
        for expected in [
            {
                "name": "urls_crawl_depth_id",
                "columns": ["crawl_depth", "id"],
                "unique": False,
                "where": "fetch_state = 'queued'",
            },
            {"name": "urls_url", "columns": ["url"], "unique": True, "where": None},
        ]
        if expected not in reduced
    ] == []


def test_the_result_counts_a_small_site(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)

    result = run_cli("crawl", server.url("/")).json()

    assert (result["state"], result["urls"], result["pages"], result["status_classes"]) == (
        "completed",
        {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0},
        3,
        {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0},
    )


def test_a_completed_crawl_exits_with_code_0(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)

    result = run_cli("crawl", server.url("/"))

    assert (result.exit_code, result.json()["state"]) == (0, "completed")


def test_the_result_has_the_fields_of_a_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)

    result = run_cli("crawl", server.base_url).json()

    assert (
        list(result),
        result["crawl_mode"],
        result["seed"],
        result["seed_count"],
        result["section_crawl"],
        result["duration_s"] >= 0,
    ) == (
        [
            "crawl_id",
            "state",
            "crawl_mode",
            "seed",
            "seed_count",
            "section_crawl",
            "started_at",
            "ended_at",
            "duration_s",
            "urls",
            "pages",
            "status_classes",
            "crawl_file",
        ],
        "spider",
        server.base_url,
        1,
        False,
        True,
    )
