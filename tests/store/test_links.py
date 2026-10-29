"""The row writer of openlinx.store.links (030-add-page-data D4; seam 2)."""

from dataclasses import fields
from datetime import UTC, datetime

from openlinx.crawl.urls import NormalizedUrl, parse_seed
from openlinx.store.links import write_links
from openlinx.store.page_records import LinkRow
from openlinx.store.records import FetchedUrl, NewUrl, Provenance
from openlinx.store.rows import HandlerRows
from openlinx.store.schema import links
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_links_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    url = parse_seed("https://site.test/")
    assert isinstance(url, str)
    target = NormalizedUrl("https://site.test/about")

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(url, is_internal=True, in_scope=True))
        # A Page that links the same target twice: each occurrence is a row of its own.
        rows = tuple(
            LinkRow(
                source_url_id=url_id,
                ordinal=ordinal,
                target=target,
                type="hyperlink",
                declared_in="body",
                element="a",
                attribute="href",
                anchor_text=anchor,
                alt_text=None,
                rel=None,
                rel_nofollow=False,
                rel_ugc=False,
                rel_sponsored=False,
                followed=True,
                hreflang=None,
                media=None,
                link_position="content",
            )
            for ordinal, anchor in ((1, "About"), (2, "About us"))
        )
        fetched = FetchedUrl(
            url_id=url_id,
            provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
            status_code=200,
            content_type="text/html",
            fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            response_time_ms=12,
            parsed=True,
            discovered=(
                NewUrl(url=target, discovered_via="hyperlink", is_internal=True, in_scope=True),
            ),
            rows=(HandlerRows(write_links, rows),),
        )
        writer.run(record_fetched(fetched))
        replay_now(writer)

    assert query(
        crawl.path,
        "SELECT links.ordinal, urls.url, links.anchor_text FROM links"
        " JOIN urls ON urls.id = links.target_url_id ORDER BY links.ordinal",
    ) == [(1, target, "About"), (2, target, "About us")]


def test_the_link_row_has_every_links_column() -> None:
    # The writer stores the row's target URL as the id of its urls row.
    row_columns = {
        "target_url_id" if field.name == "target" else field.name for field in fields(LinkRow)
    }

    assert row_columns == {column.name for column in links.c}
