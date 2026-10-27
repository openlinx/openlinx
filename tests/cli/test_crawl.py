"""`spider crawl` (020-add-crawl-core, crawling)."""

import json

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.cli import run_cli
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace

SMALL_SITE = Site(
    routes={
        "/": Page(body='<a href="/a">A</a> <a href="/b">B</a> <a href="/missing">Gone</a>'),
        "/a": Page(body="<p>A</p>"),
        "/b": Page(body="<p>B</p>"),
    }
)
ROBOTS_DOWN = Site(routes={**SMALL_SITE.routes, "/robots.txt": Status(503)})


def test_an_invalid_seed_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://exa mple.test/")
    errors = [error["code"] for error in result.errors()]

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
            "stop_reason",
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
            "warnings",
        ],
        "spider",
        server.base_url,
        1,
        False,
        True,
    )


def test_the_crawl_command_prints_one_document() -> None:
    entry = next(c for c in run_cli("commands").json()["commands"] if c["name"] == "crawl")

    assert entry["output"] == "document"


def test_the_first_event_line_is_the_start_event(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)

    result = run_cli("crawl", server.url("/"))
    first = next(line for line in result.stderr_json_lines() if "event" in line)

    assert (first["event"], first["data"]) == (
        "crawl_started",
        {
            "crawl_id": result.json()["crawl_id"],
            "crawl_mode": "spider",
            "seed_count": 1,
            "crawl_file": result.json()["crawl_file"],
            "parse_workers": 0,
        },
    )


def test_every_stderr_line_is_an_event_or_a_diagnostic(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(ROBOTS_DOWN)

    result = run_cli("crawl", server.url("/"))

    assert (result.stray_stderr_lines(), bool(result.stderr)) == ([], True)


def test_a_warning_is_written_as_a_diagnostic(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(ROBOTS_DOWN)

    lines = run_cli("crawl", server.url("/")).stderr_json_lines()

    assert [line["level"] for line in lines if line.get("code") == "robots_unreachable"] == [
        "warning"
    ]


def test_the_recorded_config_holds_every_registered_crawl_setting(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)
    entry = next(c for c in run_cli("commands").json()["commands"] if c["name"] == "crawl")
    defaults = {
        option["setting"].removeprefix("crawl."): option["default"]
        for option in entry["options"]
        if (option["setting"] or "").startswith("crawl.")
    }

    config = json.loads(crawl_row(crawled(server.url("/")))["config"])

    assert (config["crawl"], bool(defaults)) == (defaults, True)


def test_spider_toml_sets_a_crawl_setting(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)
    (temp_workspace.root / "spider.toml").write_bytes(b"[crawl]\nconcurrency = 2\n")

    config = json.loads(crawl_row(crawled(server.url("/")))["config"])

    assert config["crawl"]["concurrency"] == 2


def test_a_flag_overrides_spider_toml(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)
    (temp_workspace.root / "spider.toml").write_bytes(b"[crawl]\nconcurrency = 2\n")

    config = json.loads(crawl_row(crawled(server.url("/"), "--concurrency", "3"))["config"])

    assert config["crawl"]["concurrency"] == 3


def test_an_invalid_exclude_pattern_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--exclude", "(")
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        error["details"],
        list(temp_workspace.home.rglob("*.sqlite")),
    ) == (2, "invalid_pattern", {"pattern": "("}, [])


def test_a_concurrency_of_zero_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--concurrency", "0")
    errors = [error["code"] for error in result.errors()]

    assert (result.exit_code, errors) == (2, ["invalid_value"])


def test_a_concurrency_above_50_in_the_settings_file_is_refused(
    temp_workspace: TempWorkspace,
) -> None:
    (temp_workspace.root / "spider.toml").write_bytes(b"[crawl]\nconcurrency = 51\n")

    result = run_cli("crawl", "http://site.test/")
    errors = [error["code"] for error in result.errors()]

    assert (result.exit_code, errors) == (3, ["settings_invalid"])


def test_no_check_external_records_an_external_url_as_skipped(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # Requested, other.test would reach the network guard, which fails the test.
    server = fixture_site(Site(routes={"/": Page(body='<a href="http://other.test/">O</a>')}))

    crawl_file = crawled(server.url("/"), "--no-check-external")

    assert query(
        crawl_file,
        "SELECT fetch_state, skip_reason FROM urls WHERE url = ?",
        ["http://other.test/"],
    ) == [("skipped", "external_not_checked")]


def test_the_subdomains_shorthand_conflicts_with_a_subfolder_scope(
    temp_workspace: TempWorkspace,
) -> None:
    result = run_cli("crawl", "http://site.test/blog/", "--subdomains", "--scope", "subfolder")
    errors = [error["code"] for error in result.errors()]

    assert (result.exit_code, errors, list(temp_workspace.home.rglob("*.sqlite"))) == (
        2,
        ["option_conflict"],
        [],
    )


def test_the_subdomains_shorthand_is_the_subdomains_scope(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)

    config = json.loads(crawl_row(crawled(server.url("/"), "--subdomains"))["config"])

    assert config["crawl"]["scope"] == "subdomains"


def test_a_seed_without_its_trailing_slash_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/blog", "--scope", "subfolder")

    assert (
        result.exit_code,
        [
            (
                error["code"],
                error["details"]["suggested_seed"],
                "http://site.test/blog/ " in error["hint"],
            )
            for error in result.errors()
        ],
    ) == (2, [("subfolder_is_root", "http://site.test/blog/", True)])


def test_a_root_seed_with_a_subfolder_scope_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--scope", "subfolder")

    assert (
        result.exit_code,
        [
            (
                error["code"],
                error["details"]["suggested_seed"],
                "--scope subfolder" in error["hint"],
            )
            for error in result.errors()
        ],
        list(temp_workspace.home.rglob("*.sqlite")),
    ) == (2, [("subfolder_is_root", None, True)], [])


def test_an_invalid_pattern_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--include", "(")

    assert (
        result.exit_code,
        [(error["code"], "--include" in error["hint"]) for error in result.errors()],
        list(temp_workspace.home.rglob("*.sqlite")),
    ) == (2, [("invalid_pattern", True)], [])


def test_a_seed_outside_the_scope_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--exclude", "site")

    assert (
        result.exit_code,
        [error["code"] for error in result.errors()],
        list(temp_workspace.home.rglob("*.sqlite")),
    ) == (2, ["seed_out_of_scope"], [])


def test_a_seed_that_matches_no_include_pattern_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--include", "/blog/")

    assert (
        result.exit_code,
        [(error["code"], "--include" in error["message"]) for error in result.errors()],
    ) == (2, [("seed_out_of_scope", True)])


def test_a_subfolder_crawl_is_a_section_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/blog/": Page(body="<p>Blog</p>")}))

    result = run_cli("crawl", server.url("/blog/"), "--scope", "subfolder")

    assert (result.exit_code, result.json()["section_crawl"]) == (0, True)
