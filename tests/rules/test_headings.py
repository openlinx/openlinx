"""Verify heading Rules over Pages written by a real Crawl."""

import pytest

from openlinx.rules.headings import H1_TOO_LONG
from openlinx.rules.model import Threshold
from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.rule_cases import PageRuleCase, check_page_rule_cases
from tests.support.rule_results import assert_rule_results


@pytest.mark.usefixtures("temp_workspace")
def test_missing_h1(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        '<h1>Home</h1><a href="/missing">Missing</a>'
                        '<a href="/empty">Empty</a><a href="/present">Present</a>'
                    )
                ),
                "/missing": Page(body="<p>No main heading</p>"),
                "/empty": Page(body="<h1></h1>"),
                "/present": Page(body="<h1>Product</h1>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(missing_id, missing_count, missing_first)] = query(
        file,
        "SELECT url_id, h1_count, h1_1 FROM pages WHERE url_path = '/missing'",
    )
    [(empty_id, empty_count, empty_first)] = query(
        file,
        "SELECT url_id, h1_count, h1_1 FROM pages WHERE url_path = '/empty'",
    )
    [(present_count, present_first)] = query(
        file,
        "SELECT h1_count, h1_1 FROM pages WHERE url_path = '/present'",
    )
    assert (missing_count, missing_first) == (0, None)
    assert (empty_count, empty_first) == (1, "")
    assert (present_count, present_first) == (1, "Product")
    [rule] = [rule for rule in RULES if rule.id == "h1-missing"]

    assert sorted(evaluate_rule(file, rule), key=lambda item: item.url_id) == [
        AffectedUrl(url_id=missing_id, detail=None),
        AffectedUrl(url_id=empty_id, detail=None),
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_duplicate_h1(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<h1>Welcome</h1><a href="/same">Same</a><a href="/case">Case</a>'
                    '<a href="/noindex">Non-Indexable</a>'
                ),
                "/same": Page(body="<h1>Welcome</h1>"),
                "/case": Page(body="<h1>welcome</h1>"),
                "/noindex": Page(body='<meta name="robots" content="noindex"><h1>Welcome</h1>'),
            }
        )
    )
    check_page_rule_cases(
        server.url("/"),
        "headings",
        [
            PageRuleCase(
                id="h1-duplicate",
                issue_type="opportunity",
                priority="low",
                affected={
                    server.url("/"): {"h1_1": "Welcome", "pages": 2},
                    server.url("/same"): {"h1_1": "Welcome", "pages": 2},
                },
            )
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_multiple_h1(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<h1>Welcome</h1><a href="/multiple">Multiple</a>'),
                "/multiple": Page(body="<h1>Main</h1><h1>Two</h1><h1>Three</h1>"),
            }
        )
    )
    check_page_rule_cases(
        server.url("/"),
        "headings",
        [
            PageRuleCase(
                id="h1-multiple",
                issue_type="warning",
                priority="low",
                affected={server.url("/multiple"): {"count": 3}},
            )
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_h1_too_long(fixture_site: StartSite) -> None:
    server = fixture_site(Site({"/over-limit": Page(body="<h1>" + "a" * 71 + "</h1>")}))
    check_page_rule_cases(
        server.url("/over-limit"),
        "headings",
        [
            PageRuleCase(
                id="h1-too-long",
                issue_type="opportunity",
                priority="low",
                thresholds=(Threshold("max_chars", 70, "characters"),),
                affected={server.url("/over-limit"): {"length": 71}},
            )
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_h1_at_the_limit(fixture_site: StartSite) -> None:
    server = fixture_site(Site({"/at-limit": Page(body="<h1>" + "a" * 70 + "</h1>")}))
    file = crawled(server.url("/at-limit"))
    assert query(file, "SELECT url_path, h1_1_length FROM pages") == [("/at-limit", 70)]
    assert evaluate_rule(file, H1_TOO_LONG) == []
    assert_rule_results(file, "h1-too-long", [])


@pytest.mark.usefixtures("temp_workspace")
def test_missing_h2(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<h1>Welcome</h1><a href="/same">Empty</a><a href="/case">Present</a>'
                ),
                "/same": Page(body="<h1>Welcome</h1><h2></h2><h2>Subheading</h2>"),
                "/case": Page(body="<h1>welcome</h1><h2>Subheading</h2>"),
            }
        )
    )
    check_page_rule_cases(
        server.url("/"),
        "headings",
        [
            PageRuleCase(
                id="h2-missing",
                issue_type="opportunity",
                priority="low",
                affected={server.url("/"): None, server.url("/same"): None},
            )
        ],
    )
