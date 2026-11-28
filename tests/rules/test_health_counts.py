"""Verify which Affected URLs lower the Health Score over a real Crawl Store."""

from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.services.hooks import default_hooks
from openlinx.store.health import Health, materialised_health
from openlinx.store.reading import reading
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage


@pytest.mark.usefixtures("temp_workspace")
def test_end_to_end_score_on_the_fixture_site(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Shop</title><meta name="description" content="Our shop">'
                    '<h1>Shop</h1><a href="/boots">Boots</a><a href="/coats">Coats</a>'
                    '<a href="/no-title">Accessories</a>'
                ),
                "/boots": Page(
                    body='<title>Boots</title><meta name="description" content="Our boots">'
                    "<h1>Boots</h1>"
                ),
                "/coats": Page(
                    body='<title>Coats</title><meta name="description" content="Our coats">'
                    "<h1>Coats</h1>"
                ),
                "/no-title": Page(
                    body='<meta name="description" content="Our accessories"><h1>Accessories</h1>'
                ),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert query(file, "SELECT url_path FROM pages ORDER BY url_path") == [
        ("/",),
        ("/boots",),
        ("/coats",),
        ("/no-title",),
    ]
    assert query(
        file,
        "SELECT pages.url_path, rules.id FROM affected_urls "
        "JOIN pages USING (url_id) JOIN rules ON rules.id = affected_urls.rule_id "
        "WHERE rules.issue_type = 'issue' ORDER BY pages.url_path, rules.id",
    ) == [("/no-title", "title-missing")]
    assert query(
        file,
        "SELECT health_score, health_internal_page_count, health_affected_page_count FROM crawl",
    ) == [(75, 4, 1)]


@pytest.mark.usefixtures("temp_workspace")
def test_score_before_the_passes(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site({"/": Page(body='<meta name="description" content="Our shop"><h1>Shop</h1>')})
    )
    reporter = Collected()
    before_passes: list[tuple[object, ...]] = []

    async def observe_running_crawl(_context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(started["crawl_file"])
        assert query(file, "SELECT url_path FROM pages") == [("/",)]
        before_passes.extend(
            query(
                file,
                "SELECT state, health_score, health_internal_page_count, "
                "health_affected_page_count, health_calculated_at FROM crawl",
            )
        )

    defaults = default_hooks()
    probe = Pass("observe-running-crawl", observe_running_crawl)
    hooks = replace(defaults, passes=(probe, *defaults.passes))
    result = crawl_result(server.url("/"), hooks, reporter=reporter)

    assert before_passes == [("running", None, None, None, None)]
    assert result.summary.state == "completed"
    assert query(
        result.crawl_file,
        "SELECT health_score, health_internal_page_count, health_affected_page_count FROM crawl",
    ) == [(0, 1, 1)]


@pytest.mark.usefixtures("temp_workspace")
def test_health_calculated_at_uses_the_clock_of_the_post_crawl_pass() -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<title>Home</title>")})

    async def shift_wall(context: PassContext) -> None:
        clock.shift_wall(60)

    hooks = default_hooks()
    hooks = replace(
        hooks,
        passes=(Pass("before-issues", shift_wall), *hooks.passes, Pass("after-issues", shift_wall)),
    )
    result = crawl_result("http://site.test/", hooks, clock=clock, fetcher=fetcher)

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT health_calculated_at FROM crawl") == [
        ("2026-01-01T00:01:00.000Z",)
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_warnings_do_not_lower_the_score(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    template=True,
                    body=(
                        "<title>Shop jackets and footwear for your next trip</title>"
                        '<meta name="description" content="Find gear for your next walk, '
                        'from light layers to jackets for a full day out on the trail.">'
                        '<link rel="canonical" href="{{base_url}}/">'
                        "<h1>Outdoor shop</h1><h2>For your next trip</h2>"
                        '<a href="/boots">Boots</a>'
                        f"<p>{'Browse these styles and compare the details. ' * 30}</p>"
                    ),
                ),
                "/boots": Page(
                    template=True,
                    body=(
                        "<title>Browse our collection of walking boots</title>"
                        '<meta name="description" content="Compare walking boots '
                        'by material and fit before choosing a pair for your next hike.">'
                        '<link rel="canonical" href="{{base_url}}/boots">'
                        "<h1>Walking boots</h1><h2>Compare boot options</h2>"
                        f"<p>{'Choose comfortable boots for every kind of trip. ' * 30}</p>"
                    ),
                ),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(
        file,
        "SELECT pages.url_path, rules.id, rules.issue_type FROM affected_urls "
        "JOIN pages USING (url_id) JOIN rules ON rules.id = affected_urls.rule_id "
        "ORDER BY pages.url_path, rules.id",
    ) == [("/", "http-url", "warning"), ("/boots", "http-url", "warning")]

    with reading(file) as connection:
        assert materialised_health(connection) == Health(
            score=100, internal_pages=2, affected_pages=0
        )


@pytest.mark.usefixtures("temp_workspace")
def test_a_page_with_several_issues_counts_once(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<link rel="canonical" href="/noindex">'
                    '<a href="/noindex">Noindex</a><a href="/boots">Boots</a>'
                    '<a href="/coats">Coats</a>'
                ),
                "/noindex": Page(
                    body='<title>Noindex</title><meta name="robots" content="noindex">'
                ),
                "/boots": Page(body="<title>Boots</title>"),
                "/coats": Page(body="<title>Coats</title>"),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(
        file,
        "SELECT pages.url_path, rules.id FROM affected_urls "
        "JOIN pages USING (url_id) JOIN rules ON rules.id = affected_urls.rule_id "
        "WHERE rules.issue_type = 'issue' ORDER BY pages.url_path, rules.id",
    ) == [("/", "canonical-to-non-indexable"), ("/", "title-missing")]
    assert query(
        file,
        "SELECT state, health_score, health_internal_page_count, health_affected_page_count "
        "FROM crawl",
    ) == [("completed", 75, 4, 1)]

    with reading(file) as connection:
        assert materialised_health(connection) == Health(
            score=75, internal_pages=4, affected_pages=1
        )
