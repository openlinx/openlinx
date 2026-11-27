"""Verify meta description Rules over Pages in a real crawl store."""

import pytest

from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query


@pytest.mark.usefixtures("temp_workspace")
def test_missing_meta_description(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/empty">Empty</a><a href="/present">Present</a>'),
                "/empty": Page(
                    body='<meta name="description" content="">'
                    '<meta name="description" content="Second description">'
                    '<meta name="robots" content="noindex">'
                ),
                "/present": Page(body='<meta name="description" content="Buy shoes">'),
            }
        )
    )
    file = crawled(server.url("/"))
    rows = query(
        file,
        "SELECT url_path, url_id, meta_description_count, meta_description_1, "
        "meta_description_2, indexability_status FROM pages ORDER BY url_path",
    )
    measurements = [
        (path, count, first, second, status) for path, _, count, first, second, status in rows
    ]
    assert measurements == [
        ("/", 0, None, None, None),
        ("/empty", 2, "", "Second description", "noindex"),
        ("/present", 1, "Buy shoes", None, None),
    ]
    paths = {url_id: path for path, url_id, *_ in rows}
    matching = [rule for rule in RULES if rule.id == "meta-description-missing"]
    assert len(matching) == 1, "The catalogue must register meta-description-missing once"
    [rule] = matching
    assert (rule.category, rule.issue_type, rule.priority, rule.applies_to, rule.thresholds) == (
        "meta_descriptions",
        "opportunity",
        "medium",
        "internal_pages",
        (),
    )

    affected = [(paths[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=lambda item: item[0]) == [("/", None), ("/empty", None)]
