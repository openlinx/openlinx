"""Verify heading Rules over Pages written by a real Crawl."""

import pytest

from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query


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
