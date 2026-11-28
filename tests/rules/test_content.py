"""Verify Content Rules on measurements recorded by real Crawls."""

import json
from contextlib import closing
from dataclasses import replace

import pytest

from openlinx.clock import SystemClock
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides, CrawlRequest, plan_crawl, start_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.connections import connect
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
from tests.support.crawl_store import crawl_store
from tests.support.crawling import continued, crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.rule_results import assert_rule_results
from tests.support.workspace import TempWorkspace


@pytest.mark.usefixtures("temp_workspace")
def test_thin_page(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        '<nav><a href="/at">At</a><a href="/below">Below</a>'
                        '<a href="/noindex">Noindex</a><a href="/zero">Zero</a></nav>'
                        f"<main><p>{'word ' * 200}</p></main>"
                    )
                ),
                "/at": Page(body=f"<p>{'word ' * 200}</p>"),
                "/below": Page(body=f"<p>{'word ' * 199}</p>"),
                "/noindex": Page(
                    body=(f'<meta name="robots" content="noindex"><p>{"word " * 10}</p>')
                ),
                "/zero": Page(body="<title>Empty Content Area</title>"),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(
        file,
        "SELECT url, indexability, word_count FROM urls JOIN pages ON pages.url_id = urls.id "
        "ORDER BY url",
    ) == [
        (server.url("/"), "indexable", 200),
        (server.url("/at"), "indexable", 200),
        (server.url("/below"), "indexable", 199),
        (server.url("/noindex"), "non_indexable", 10),
        (server.url("/zero"), "indexable", 0),
    ]
    assert_rule_results(
        file,
        "low-word-count",
        [(server.url("/below"), {"word_count": 199}), (server.url("/zero"), {"word_count": 0})],
    )


def test_word_count_at_the_minimum(temp_workspace: TempWorkspace) -> None:
    url = "https://example.com/at"
    file = crawl_store(temp_workspace, pages={url: f"<p>{'word ' * 200}</p>"})

    assert query(
        file,
        "SELECT indexability, word_count FROM urls JOIN pages ON pages.url_id = urls.id "
        "WHERE url = ?",
        (url,),
    ) == [("indexable", 200)]
    assert_rule_results(file, "low-word-count", [("https://example.com/", {"word_count": 3})])


def test_thin_noindex_page_is_ignored(temp_workspace: TempWorkspace) -> None:
    url = "https://example.com/noindex"
    body = f'<meta name="robots" content="noindex"><p>{"word " * 10}</p>'
    file = crawl_store(temp_workspace, pages={url: body})

    assert query(
        file,
        "SELECT indexability_status, word_count FROM urls JOIN pages ON pages.url_id = urls.id "
        "WHERE url = ?",
        (url,),
    ) == [("noindex", 10)]
    assert_rule_results(file, "low-word-count", [("https://example.com/", {"word_count": 3})])


@pytest.mark.usefixtures("temp_workspace")
def test_exact_duplicates(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        '<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'
                        '<a href="/empty">Empty</a><a href="/other-empty">Other empty</a>'
                        '<a href="/noindex">Noindex</a><a href="/different">Different</a>'
                    )
                ),
                "/a": Page(body="<p>Hello world</p>"),
                "/b": Page(body="<p>Hello world</p>"),
                "/c": Page(body="<p>Hello world</p>"),
                "/different": Page(body="<p>Hello World</p>"),
                "/empty": Page(body="<title>No content</title>"),
                "/other-empty": Page(body="<title>Also empty</title>"),
                "/noindex": Page(body='<meta name="robots" content="noindex"><p>Hello world</p>'),
            }
        )
    )
    file = crawled(server.url("/"))
    digest = "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"

    assert query(
        file,
        "SELECT url, indexability, content_hash FROM urls JOIN pages ON pages.url_id = urls.id "
        "WHERE url <> ? ORDER BY url",
        (server.url("/"),),
    ) == [
        (server.url("/a"), "indexable", digest),
        (server.url("/b"), "indexable", digest),
        (server.url("/c"), "indexable", digest),
        (
            server.url("/different"),
            "indexable",
            "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
        ),
        (server.url("/empty"), "indexable", None),
        (server.url("/noindex"), "non_indexable", digest),
        (server.url("/other-empty"), "indexable", None),
    ]
    assert_rule_results(
        file,
        "exact-duplicate",
        [
            (server.url("/a"), {"content_hash": digest, "pages": 3}),
            (server.url("/b"), {"content_hash": digest, "pages": 3}),
            (server.url("/c"), {"content_hash": digest, "pages": 3}),
        ],
    )

    [(noindex_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/noindex"),))
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = 'exact-duplicate'")
    # Use the live reader's URL filter over the trusted SQL recorded by this test's Crawl.
    select_url = f"SELECT detail FROM ({sql}) WHERE url_id = ?"  # noqa: S608
    ticks = 0

    def count() -> int:
        nonlocal ticks
        ticks += 1
        return 0

    with closing(connect(file, read_only=True)) as connection:
        assert connection.execute(select_url, (noindex_id,)).fetchall() == []
        connection.set_progress_handler(count, 250)
        assert connection.execute(select_url, (noindex_id,)).fetchall() == []
    # Rejecting a noindex Page needs only its Page and URL records.
    assert ticks == 0, ticks


def test_pages_without_a_hash_are_not_duplicates(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/empty": "<title>No content</title>",
            "https://example.com/other-empty": "<title>Also empty</title>",
        },
    )

    assert query(
        file,
        "SELECT url, indexability, content_hash FROM urls JOIN pages ON pages.url_id = urls.id "
        "WHERE url <> ? ORDER BY url",
        ("https://example.com/",),
    ) == [
        ("https://example.com/empty", "indexable", None),
        ("https://example.com/other-empty", "indexable", None),
    ]
    assert_rule_results(file, "exact-duplicate", [])


@pytest.fixture
def word_count_site(fixture_site: StartSite) -> ServerHandle:
    return fixture_site(
        Site(
            {
                "/": Page(
                    body=f'<nav><a href="/next">Next</a></nav><main><p>{"word " * 350}</p></main>'
                ),
                "/next": Page(body=f"<p>{'word ' * 120}</p>"),
            }
        )
    )


def test_raising_the_word_count_threshold_after_completion_preserves_existing_results(
    temp_workspace: TempWorkspace, word_count_site: ServerHandle
) -> None:
    seed = word_count_site.url("/")
    next_url = word_count_site.url("/next")
    original = crawl_result(seed)
    assert original.summary.state == "completed"
    [(thresholds,)] = query(
        original.crawl_file, "SELECT thresholds FROM rules WHERE id = 'low-word-count'"
    )
    assert json.loads(thresholds) == {"min_words": 200}
    expected_thin_page = (next_url, {"word_count": 120})
    assert_rule_results(original.crawl_file, "low-word-count", [expected_thin_page])

    (temp_workspace.root / "openlinx.toml").write_text(
        "[rules.low-word-count]\nmin_words = 5000\n", encoding="utf-8"
    )
    fresh = crawl_result(seed)
    assert fresh.summary.state == "completed"
    assert fresh.crawl_file != original.crawl_file
    assert_rule_results(
        fresh.crawl_file, "low-word-count", [(seed, {"word_count": 350}), expected_thin_page]
    )
    assert_rule_results(original.crawl_file, "low-word-count", [expected_thin_page])


def test_resumed_crawl_applies_its_original_word_count_threshold(
    temp_workspace: TempWorkspace, word_count_site: ServerHandle
) -> None:
    seed = word_count_site.url("/")
    next_url = word_count_site.url("/next")
    settings = temp_workspace.root / "openlinx.toml"
    settings.write_text("[rules.low-word-count]\nmin_words = 300\n", encoding="utf-8")
    stopped = crawl_result(seed, max_urls=1)
    assert stopped.summary.state == "stopped"
    assert [(request.method, request.path) for request in word_count_site.requests] == [
        ("GET", "/robots.txt"),
        ("GET", "/"),
    ]
    settings.write_text("[rules.low-word-count]\nmin_words = 50\n", encoding="utf-8")

    result = continued(stopped, CrawlOverrides(max_urls=None))
    assert result.summary.state == "completed"
    assert result.crawl_file == stopped.crawl_file
    [(thresholds,)] = query(
        result.crawl_file, "SELECT thresholds FROM rules WHERE id = 'low-word-count'"
    )
    assert json.loads(thresholds) == {"min_words": 300}
    assert query(
        result.crawl_file,
        "SELECT indexability, word_count FROM pages WHERE address = ?",
        (next_url,),
    ) == [("indexable", 120)]
    assert_rule_results(result.crawl_file, "low-word-count", [(next_url, {"word_count": 120})])


def test_continue_does_not_add_content_rules_to_an_older_snapshot(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Start</title><nav><a href="/next">Next</a></nav>'
                    "<main><p>Short</p></main>"
                ),
                "/next": Page(body="<p>Short</p>"),
            }
        )
    )
    seed = server.url("/")
    plan = plan_crawl(
        CrawlRequest(
            seed=seed,
            cwd=temp_workspace.root,
            home=temp_workspace.home,
            workspace=None,
            command_argv=["linx", "crawl", seed],
            flags={"crawl": {"max_urls": 1}},
            secret_flags={},
        )
    )
    # Model the older catalogue at creation so both snapshots agree before the first pass.
    content_ids = {"low-word-count", "exact-duplicate"}
    config = {
        **plan.new_crawl.config,
        "rules": {
            rule_id: settings
            for rule_id, settings in plan.new_crawl.config["rules"].items()
            if rule_id not in content_ids
        },
    }
    planned_rules = [rule for rule in plan.new_crawl.rules if rule.id not in content_ids]
    previous = replace(plan.new_crawl, config=config, rules=planned_rules)
    stopped = start_crawl(
        replace(plan, new_crawl=previous), SystemClock(), Collected(), default_hooks(plan.loaded)
    )
    assert stopped.summary.state == "stopped"
    file = stopped.crawl_file
    original = query(file, "SELECT * FROM rules ORDER BY id")

    completed = continued(stopped, CrawlOverrides(max_urls=None))

    assert completed.summary.state == "completed"
    assert query(file, "SELECT * FROM rules ORDER BY id") == original
    assert json.loads(crawl_row(file)["config"])["rules"] == config["rules"]
    assert query(
        file,
        "SELECT url, indexability, word_count FROM urls JOIN pages ON pages.url_id = urls.id "
        "WHERE url = ?",
        (server.url("/next"),),
    ) == [(server.url("/next"), "indexable", 1)]
    assert (
        query(
            file,
            "SELECT rule_id FROM affected_urls WHERE rule_id IN (?, ?)",
            ("low-word-count", "exact-duplicate"),
        )
        == []
    )
    assert_rule_results(file, "title-missing", [(server.url("/next"), None)])
