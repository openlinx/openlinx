"""Verify response-code Rules over URLs written by a real Crawl."""

import pytest

from openlinx.rules.response_codes import INTERNAL_4XX
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawled
from tests.support.crawls import query


@pytest.mark.usefixtures("temp_workspace")
def test_client_error(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/section/": Page(
                    body='<a href="/gone">Gone</a>'
                    '<a href="/section/before">Before the range</a>'
                    '<a href="/section/first">First client error</a>'
                    '<a href="/section/last">Last client error</a>'
                    '<a href="/section/after">After the range</a>'
                ),
                "/gone": Status(404, body="Not found"),
                "/section/before": Status(399),
                "/section/first": Status(400),
                "/section/last": Status(499),
                "/section/after": Status(500),
            }
        )
    )
    file = crawled(server.url("/section/"), "--scope", "subfolder", "--retries", "0")
    statuses = query(
        file,
        "SELECT id, is_internal, in_scope, fetch_state, status_code FROM urls "
        "WHERE url != ? ORDER BY status_code",
        (server.url("/section/"),),
    )
    assert [row[1:] for row in statuses] == [
        (1, 1, "fetched", 399),
        (1, 1, "fetched", 400),
        (1, 0, "fetched", 404),
        (1, 1, "fetched", 499),
        (1, 1, "fetched", 500),
    ]
    _, first, gone, last, _ = (row[0] for row in statuses)
    affected = evaluate_rule(file, INTERNAL_4XX)

    assert sorted(affected, key=lambda row: row.url_id) == sorted(
        [
            AffectedUrl(url_id=first, detail={"status_code": 400}),
            AffectedUrl(url_id=gone, detail={"status_code": 404}),
            AffectedUrl(url_id=last, detail={"status_code": 499}),
        ],
        key=lambda row: row.url_id,
    )
