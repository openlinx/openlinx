"""Verify title Rules over Pages written by a real Crawl."""

import pytest

from openlinx.rules.titles import TITLE_MISSING
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query


@pytest.mark.usefixtures("temp_workspace")
def test_missing_title_produces_an_affected_url(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/missing">Missing</a>'),
                "/missing": Page(body="<p>No title</p>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(missing_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/missing"),))

    assert evaluate_rule(file, TITLE_MISSING) == [AffectedUrl(url_id=missing_id, detail=None)]


@pytest.mark.usefixtures("temp_workspace")
def test_empty_title_counts_as_missing(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Present</title><a href="/empty">Empty title</a>'),
                "/empty": Page(body="<title></title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(empty_id, title_count, title_1)] = query(
        file, "SELECT url_id, title_count, title_1 FROM pages WHERE url_path = '/empty'"
    )
    assert (title_count, title_1) == (1, "")

    assert evaluate_rule(file, TITLE_MISSING) == [AffectedUrl(url_id=empty_id, detail=None)]
