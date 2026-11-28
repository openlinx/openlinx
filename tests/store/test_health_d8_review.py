"""Exercise D8 selection boundaries in both affected-URL sources."""

import pytest
from sqlalchemy import Connection, literal, select, union_all
from sqlalchemy.sql import FromClause

from openlinx.rules.registry import RULES
from openlinx.store.health import Health, health_for_pages
from openlinx.store.issues import affected_urls_in, affected_urls_unit
from openlinx.store.reading import reading
from openlinx.store.schema import affected_urls, urls
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.workspace import TempWorkspace

_RULE_IDS = ("title-missing", "canonical-to-non-indexable", "h1-missing", "internal-4xx")
_RESOURCE = "https://example.com/assets/broken.png"


def _record_selected_404_and_resource(connection: Connection) -> None:
    connection.exec_driver_sql("UPDATE pages SET status_code = 404 WHERE url_path = '/products/d'")
    connection.exec_driver_sql(
        "UPDATE urls SET status_code = 404 WHERE url = 'https://example.com/products/d'"
    )
    connection.exec_driver_sql(
        """
        INSERT INTO urls (origin_id, host, url, is_internal, in_scope, crawl_depth,
                          discovered_via, found_on_url_id, fetch_state, status_code,
                          content_type, parsed, attempt_count, fetched_at)
        SELECT origin_id, host, ?, 1, 1, 1, 'image', id, 'fetched', 404, 'image/png', 0,
               1, fetched_at
        FROM urls WHERE url = 'https://example.com/'
        """,
        (_RESOURCE,),
    )


@pytest.mark.parametrize("completed", [True, False], ids=["materialised", "live"])
def test_d8_counts_only_unique_internal_pages(
    temp_workspace: TempWorkspace, completed: bool
) -> None:
    file = crawl_store(
        temp_workspace,
        completed=completed,
        pages={
            "https://example.com/products/a": "<title>A</title><h1>A</h1>",
            "https://example.com/products/b": ('<link rel="canonical" href="/noindex"><h1>B</h1>'),
            "https://example.com/products/c": "<title>C</title>",
            "https://example.com/products/d": "<title>D</title><h1>D</h1>",
            "https://example.com/noindex": (
                '<title>Target</title><meta name="robots" content="noindex"><h1>Target</h1>'
            ),
            "https://example.com/outside": "<h1>Outside</h1>",
        },
    )
    with CrawlWriter(file, FakeClock()) as writer:
        writer.run(_record_selected_404_and_resource)
        if completed:
            writer.run(
                affected_urls_unit(next(rule for rule in RULES if rule.id == "internal-4xx"))
            )

    # A caller can produce duplicate ids via joins and can include URLs that have no Page.
    candidates = union_all(
        select(urls.c.id).where(urls.c.url.like("https://example.com/products/%")),
        select(urls.c.id).where(urls.c.url == "https://example.com/products/b"),
        select(urls.c.id).where(urls.c.url == _RESOURCE),
    ).subquery()
    selected = select(candidates.c.id)
    resource_only = select(urls.c.id).where(urls.c.url == _RESOURCE)

    with reading(file, snapshot=True) as connection:
        affected: FromClause
        if completed:
            affected = affected_urls
        else:
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM affected_urls").scalar_one() == 0
            )
            branches = []
            for rule_id in _RULE_IDS:
                found = affected_urls_in(connection, rule_id, RULES).subquery()
                branches.append(select(found.c.url_id, literal(rule_id).label("rule_id")))
            affected = union_all(*branches).subquery()

        affected_names = set(
            connection.execute(
                select(urls.c.url, affected.c.rule_id)
                .select_from(affected.join(urls, affected.c.url_id == urls.c.id))
                .where(affected.c.rule_id.in_(_RULE_IDS))
            )
        )
        assert affected_names == {
            ("https://example.com/products/b", "title-missing"),
            ("https://example.com/products/b", "canonical-to-non-indexable"),
            ("https://example.com/products/c", "h1-missing"),
            ("https://example.com/products/d", "internal-4xx"),
            ("https://example.com/outside", "title-missing"),
            (_RESOURCE, "internal-4xx"),
        }

        result = health_for_pages(connection, page_ids=selected, affected=affected)
        empty = health_for_pages(connection, page_ids=resource_only, affected=affected)

    assert result == Health(score=50, internal_pages=4, affected_pages=2)
    assert empty == Health(score=None, internal_pages=0, affected_pages=0)
