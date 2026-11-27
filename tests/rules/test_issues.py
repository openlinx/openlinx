"""Read stored Issue counts and verify per-Rule replacement on Writer replay."""

import json
import threading
from dataclasses import replace
from decimal import Decimal
from http.client import HTTPConnection
from operator import itemgetter
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import Connection, Engine, event

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.rules.registry import RULES
from openlinx.rules.titles import TITLE_MISSING, TITLE_TOO_LONG
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import affected_urls_unit, evaluate_rule, read_issues
from openlinx.store.records import AffectedUrl
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.cli import await_event, start_cli_process
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now

RULE_PAGES = Site(
    {
        "/rules/": Page(
            body='<title>Rules</title><a href="/rules/untitled">Untitled</a>'
            '<a href="/rules/gone">Gone</a>'
        ),
        "/rules/untitled": Page(body="<p>Missing title</p>"),
        "/rules/gone": Status(404, body="Not found", content_type="text/plain"),
    }
)
DUPLICATE_TITLE_PAGES = Site(
    {
        "/rules/": Page(body='<title>Shoes</title><a href="/rules/trainers">Trainers</a>'),
        "/rules/trainers": Page(body='<title>Shoes</title><a href="/rules/">Shoes</a>'),
    }
)


@pytest.fixture
def issue_crawl(temp_workspace: TempWorkspace, fixture_site: StartSite) -> tuple[Path, str]:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/second">Second</a><a href="/titled">Titled</a>'),
                "/second": Page(body="<p>No title</p>"),
                "/titled": Page(body="<title>Present</title>"),
            }
        )
    )
    return crawled(server.url("/")), server.url("/")


def stored_missing_titles(file: Path) -> list[tuple[str, None]]:
    return query(
        file,
        "SELECT u.url, a.detail FROM affected_urls AS a JOIN urls AS u ON a.url_id = u.id "
        "WHERE a.rule_id = 'title-missing' ORDER BY u.url",
    )


def missing_title_issue(file: Path) -> list[tuple[str, str, str, int]]:
    return query(
        file,
        "SELECT category, issue_type, priority, affected_count FROM issues "
        "WHERE rule_id = 'title-missing'",
    )


def test_issue_row_counts_its_affected_urls(issue_crawl: tuple[Path, str]) -> None:
    file, root = issue_crawl
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert stored_missing_titles(file) == [(root, None), (root + "second", None)]
    assert missing_title_issue(file) == [("titles", "issue", "high", 2)]


@pytest.mark.usefixtures("temp_workspace")
def test_detail_is_stored_as_json(fixture_site: StartSite) -> None:
    title = "Buy running shoes, trail boots and sandals online at low cost"
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/long-title">Shoes</a>'),
                "/long-title": Page(body=f"<title>{title}</title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    [(url_id, address, detail)] = query(
        file,
        "SELECT affected_urls.url_id, urls.url, affected_urls.detail FROM affected_urls "
        "JOIN urls ON urls.id = affected_urls.url_id WHERE rule_id = 'title-too-long'",
    )
    assert address == server.url("/long-title")
    assert isinstance(detail, str)
    assert json.loads(detail) == {"length": 61}
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = 'title-too-long'")
    assert _decoded_details(query(file, sql)) == _decoded_details([(url_id, detail)])


@pytest.mark.usefixtures("temp_workspace")
def test_rule_that_did_not_fire_has_no_issue(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/rules/": Page(
                    body='<title>Shop</title><h1>Shop</h1><a href="/rules/shoes">Shoes</a>',
                ),
                "/rules/shoes": Page(body="<title>Shoes</title><p>Running shoes</p>"),
            }
        )
    )
    file = crawled(server.url("/rules/"))

    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert query(
        file,
        "SELECT pages.url_path, pages.title_1 FROM pages JOIN urls ON urls.id = pages.url_id "
        "WHERE urls.parsed = 1 ORDER BY pages.url_path",
    ) == [("/rules/", "Shop"), ("/rules/shoes", "Shoes")]
    assert query(file, "SELECT enabled FROM rules WHERE id = 'title-missing'") == [(1,)]
    assert query(
        file,
        "SELECT rule_id, affected_count FROM issues "
        "WHERE rule_id IN ('h1-missing', 'title-missing') ORDER BY rule_id",
    ) == [("h1-missing", 1)]


@pytest.mark.usefixtures("temp_workspace")
def test_duplicates_found_by_the_post_crawl_passes(fixture_site: StartSite) -> None:
    server = fixture_site(DUPLICATE_TITLE_PAGES)
    reporter = Collected()
    inlinks_before_issues: list[list[tuple[Any, ...]]] = []

    async def record_inlinks(_context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        inlinks_before_issues.append(
            query(
                Path(started["crawl_file"]), "SELECT url_path, inlinks FROM pages ORDER BY url_path"
            )
        )

    defaults = default_hooks()
    # Both passes leave stored results, so observe the counts just before Issues runs.
    passes: list[Pass] = []
    for crawl_pass in defaults.passes:
        if crawl_pass.name == "issues":
            passes.append(Pass("record-inlinks-before-issues", record_inlinks))
        passes.append(crawl_pass)
    hooks = replace(defaults, passes=tuple(passes))
    file = crawl_result(server.url("/rules/"), hooks, reporter=reporter).crawl_file

    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    stored = query(
        file,
        "SELECT urls.url, affected_urls.detail FROM affected_urls "
        "JOIN urls ON urls.id = affected_urls.url_id "
        "WHERE affected_urls.rule_id = 'title-duplicate' ORDER BY urls.url",
    )
    assert [(url, json.loads(detail)) for url, detail in stored] == [
        (server.url("/rules/"), {"title_1": "Shoes", "pages": 2}),
        (server.url("/rules/trainers"), {"title_1": "Shoes", "pages": 2}),
    ]
    assert inlinks_before_issues == [[("/rules/", 1), ("/rules/trainers", 1)]]


@pytest.mark.usefixtures("temp_workspace")
def test_a_running_crawl_writes_no_affected_url(fixture_site: StartSite) -> None:
    server = fixture_site(DUPLICATE_TITLE_PAGES)
    reporter = Collected()
    live_counts: list[int] = []

    async def observe_running_crawl(_context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(started["crawl_file"])
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert query(file, "SELECT url_path, title_1 FROM pages ORDER BY url_path") == [
            ("/rules/", "Shoes"),
            ("/rules/trainers", "Shoes"),
        ]
        live_counts.extend(
            issue.affected_count
            for issue in read_issues(file, RULES)
            if issue.rule_id == "title-duplicate"
        )
        assert query(file, "SELECT rule_id, url_id FROM affected_urls") == []

    defaults = default_hooks()
    # Read committed Pages before any built-in pass can write Affected URLs.
    probe = Pass("observe-running-crawl", observe_running_crawl)
    hooks = replace(defaults, passes=(probe, *defaults.passes))
    result = crawl_result(server.url("/rules/"), hooks, reporter=reporter)

    assert live_counts == [2]
    assert result.summary.state == "completed"


@pytest.mark.usefixtures("temp_workspace")
def test_a_second_pass_does_not_duplicate_rows(fixture_site: StartSite) -> None:
    server = fixture_site(DUPLICATE_TITLE_PAGES)
    reporter = Collected()
    defaults = default_hooks()
    (issues_pass,) = (crawl_pass for crawl_pass in defaults.passes if crawl_pass.name == "issues")
    expected = [
        (server.url("/rules/"), {"title_1": "Shoes", "pages": 2}),
        (server.url("/rules/trainers"), {"title_1": "Shoes", "pages": 2}),
    ]
    sql = (
        "SELECT urls.url, affected_urls.detail FROM affected_urls "
        "JOIN urls ON urls.id = affected_urls.url_id "
        "WHERE affected_urls.rule_id = 'title-duplicate' ORDER BY urls.url"
    )
    passes_observed = []

    async def run_issues_twice(context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(started["crawl_file"])
        assert query(file, sql) == []

        for pass_number in (1, 2):
            await issues_pass.run(context)
            await context.writer.flush_async()
            stored = query(file, sql)
            assert [(url, json.loads(detail)) for url, detail in stored] == expected, (
                f"after Issues pass {pass_number}"
            )
            passes_observed.append(pass_number)

    repeated_issues = Pass("repeat-issues", run_issues_twice)
    hooks = replace(
        defaults,
        passes=tuple(repeated_issues if item is issues_pass else item for item in defaults.passes),
    )
    result = crawl_result(server.url("/rules/"), hooks, reporter=reporter)

    assert result.summary.state == "completed"
    assert passes_observed == [1, 2]


def test_replay_replaces_only_the_affected_urls_of_one_rule(
    issue_crawl: tuple[Path, str],
) -> None:
    file, root = issue_crawl

    def seed_previous_result(connection: Connection) -> None:
        connection.exec_driver_sql("DELETE FROM affected_urls WHERE rule_id = 'title-missing'")
        for rule in ("title-missing", "internal-4xx"):
            connection.exec_driver_sql(
                "INSERT INTO affected_urls(rule_id, url_id, detail) "
                "SELECT ?, id, NULL FROM urls WHERE url = ?",
                (rule, root + "titled"),
            )

    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(seed_previous_result)
        writer.flush()
        assert missing_title_issue(file) == [("titles", "issue", "high", 1)]

        unit = affected_urls_unit(TITLE_MISSING)
        writer.run(unit)
        writer.run(unit)
        assert stored_missing_titles(file) == [(root + "titled", None)]
        replay_now(writer)

    assert stored_missing_titles(file) == [(root, None), (root + "second", None)]
    assert missing_title_issue(file) == [("titles", "issue", "high", 2)]
    assert query(
        file,
        "SELECT url FROM urls JOIN affected_urls ON url_id = id "
        "WHERE rule_id = 'internal-4xx' AND url = ?",
        (root + "titled",),
    ) == [(root + "titled",)]


def _json_number(token: str) -> tuple[Decimal]:
    # A tuple keeps JSON numbers distinct from booleans. JSON arrays decode as lists.
    return (Decimal(token),)


def _decoded_details(rows: list[tuple[Any, ...]]) -> list[tuple[int, object]]:
    decoded = []
    for url_id, detail in sorted(rows, key=itemgetter(0)):
        value = None
        if detail is not None:
            value = json.loads(detail, parse_int=_json_number, parse_float=_json_number)
            assert isinstance(value, dict), f"expected a JSON object in detail, got {detail!r}"
        decoded.append((url_id, value))
    return decoded


@pytest.mark.usefixtures("temp_workspace")
def test_a_rule_s_query_returns_its_stored_affected_urls(fixture_site: StartSite) -> None:
    server = fixture_site(RULE_PAGES)
    file = crawled(server.url("/rules/"))

    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert (server.url("/rules/untitled"), None) in stored_missing_titles(file)
    rules = dict(query(file, "SELECT id, reproduce_sql FROM rules WHERE enabled = 1"))
    assert {"title-missing", "internal-4xx"} <= rules.keys()
    assert query(
        file,
        "SELECT url FROM affected_urls JOIN urls ON urls.id = affected_urls.url_id "
        "WHERE rule_id = 'internal-4xx'",
    ) == [(server.url("/rules/gone"),)]
    for rule_id, sql in rules.items():
        stored = query(
            file, "SELECT url_id, detail FROM affected_urls WHERE rule_id = ?", (rule_id,)
        )
        assert _decoded_details(query(file, sql)) == _decoded_details(stored), rule_id


@pytest.fixture
def live_issue_crawl(issue_crawl: tuple[Path, str]) -> Path:
    file, _ = issue_crawl

    def set_running_fixture(connection: Connection) -> None:
        connection.exec_driver_sql("UPDATE crawl SET state = 'running', completed_at = NULL")

    # These scenarios supply their own queries and need the live reader on a populated file.
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(set_running_fixture)
    assert query(file, "SELECT state FROM crawl") == [("running",)]
    return file


def test_live_issues_do_not_mix_rule_counts_across_a_writer_commit(
    live_issue_crawl: Path,
) -> None:
    file = live_issue_crawl
    assert query(file, "PRAGMA journal_mode") == [("wal",)]
    too_long = replace(
        TITLE_TOO_LONG,
        reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND length(pages.title_1) > 60""",
    )
    writer = CrawlWriter(file, FakeClock())
    reader_thread = threading.get_ident()
    committed = False

    def after_query(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal committed
        if (
            threading.get_ident() == reader_thread
            and not committed
            and statement.lstrip().upper().startswith("SELECT")
        ):
            committed = True

            def add_long_title(connection: Connection) -> None:
                connection.exec_driver_sql(
                    "UPDATE pages SET title_count = 1, title_1 = ? "
                    "WHERE url_id = (SELECT url_id FROM pages WHERE title_count = 0 LIMIT 1)",
                    ("x" * 61,),
                )

            writer.run(add_long_title)
            writer.flush()

    event.listen(Engine, "after_cursor_execute", after_query)
    try:
        with writer:
            issues = read_issues(file, (TITLE_MISSING, too_long))
    finally:
        event.remove(Engine, "after_cursor_execute", after_query)

    assert committed
    assert query(file, "SELECT COUNT(*) FROM pages WHERE title_count = 0") == [(1,)]
    assert query(file, "SELECT COUNT(*) FROM pages WHERE length(title_1) > 60") == [(1,)]
    assert [(issue.rule_id, issue.affected_count) for issue in issues] == [("title-missing", 2)]


def test_live_issues_keep_catalogue_order_and_omit_empty_rules(
    live_issue_crawl: Path,
) -> None:
    file = live_issue_crawl
    all_pages = replace(
        TITLE_TOO_LONG,
        reproduce_sql="SELECT url_id, NULL AS detail FROM pages",
    )
    no_pages = replace(
        TITLE_TOO_LONG,
        reproduce_sql="SELECT url_id, NULL AS detail FROM pages WHERE 0",
    )

    issues = read_issues(file, (all_pages, TITLE_MISSING))

    assert [(issue.rule_id, issue.affected_count) for issue in issues] == [
        ("title-too-long", 3),
        ("title-missing", 2),
    ]
    assert read_issues(file, (no_pages,)) == []


LIVE_ISSUES_SITE = Site(
    {
        "/": Page(body='<title>Home</title><h2>Home</h2><a href="/notitle">Next</a>'),
        "/notitle": Page(body='<h2>Untitled</h2><a href="/slow">Next</a>'),
        "/slow": Page(body="<title>Slow</title><h2>Slow</h2>", after="/release-slow", delay=5),
        "/release-slow": Status(code=204),
    }
)


@pytest.mark.slow
def test_issue_visible_before_the_crawl_ends(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LIVE_ISSUES_SITE)
    process = start_cli_process("crawl", server.url("/"), "--concurrency", "1", "--timeout", "30")
    held = False
    try:
        file = Path(await_event(process, "crawl_started")["crawl_file"])
        deadline = monotonic() + 8
        while True:
            committed = query(
                file,
                """SELECT pages.url_id, crawl.state, pages.title_count,
                          EXISTS(SELECT 1 FROM affected_urls)
                   FROM pages JOIN urls ON urls.id = pages.url_id CROSS JOIN crawl
                   WHERE urls.url = ?""",
                (server.url("/notitle"),),
            )
            requested = [request.path for request in server.requests]
            held = "/slow" in requested
            if committed and held:
                break
            assert process.poll() is None, "Crawl ended before the fixture was ready"
            assert monotonic() < deadline, f"no committed Page and held request: {requested!r}"
            sleep(0.02)

        [(url_id, state, title_count, materialised)] = committed
        assert (state, title_count, materialised, process.poll(), "/release-slow" in requested) == (
            "running",
            0,
            0,
            None,
            False,
        )
        assert evaluate_rule(file, TITLE_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]

        from openlinx.store.issues import read_affected_urls

        issues = [(issue.rule_id, issue.affected_count) for issue in read_issues(file, RULES)]
        affected = read_affected_urls(file, "title-missing", RULES)
        urls = [
            query(file, "SELECT url FROM urls WHERE id = ?", (item.url_id,))[0][0]
            for item in affected
        ]
        assert (issues, urls) == (
            [
                ("http-url", 2),
                ("title-missing", 1),
                ("meta-description-missing", 2),
                ("h1-missing", 2),
            ],
            [server.url("/notitle")],
        )
    finally:
        try:
            if held:
                address = urlsplit(server.base_url)
                assert address.hostname is not None
                release = HTTPConnection(address.hostname, address.port, timeout=2)
                try:
                    release.request("GET", "/release-slow")
                    with release.getresponse() as response:
                        assert response.status == 204
                finally:
                    release.close()
            if process.poll() is None:
                out, err = process.communicate(timeout=20)
                assert process.returncode == 0, err
                assert json.loads(out)["state"] == "completed"
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
