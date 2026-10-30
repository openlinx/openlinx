"""The row writer of openlinx.store.links (030-add-page-data D4; seam 2)."""

from dataclasses import fields
from datetime import UTC, datetime

from sqlalchemy import Connection

from openlinx.crawl.urls import NormalizedUrl, parse_seed
from openlinx.store.links import (
    inlink_counts,
    inlink_ranges,
    pages_with_status_200,
    write_links,
)
from openlinx.store.page_records import LinkRow, PageRow
from openlinx.store.pages import write_pages
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


# More Pages than one unit holds, and 9 of them link to the first: 100 * 9 / 12000 is 0.075,
# which a double holds as 0.07499..., so only exact arithmetic rounds it half up to 0.08.
_PAGES = 12_000
_SOURCES = 9


def _page(url_id: int, url: str) -> PageRow:
    return PageRow(
        url_id=url_id,
        address=url,
        url_encoded_address=url,
        url_path=url.removeprefix("https://site.test"),
        url_query=None,
        folder_depth=1,
        content_type="text/html",
        status_code=200,
        status="OK",
        indexability="indexable",
        indexability_status=None,
        response_time_ms=12,
        last_modified=None,
        redirect_url=None,
        redirect_type=None,
        set_cookie_count=0,
        crawl_timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def _link(source_url_id: int, target: str) -> LinkRow:
    return LinkRow(
        source_url_id=source_url_id,
        ordinal=1,
        target=target,
        type="hyperlink",
        declared_in="body",
        element="a",
        attribute="href",
        anchor_text="Home",
        alt_text=None,
        rel=None,
        rel_nofollow=False,
        rel_ugc=False,
        rel_sponsored=False,
        followed=True,
        hreflang=None,
        media=None,
        link_position="navigation",
    )


def _store_site(connection: Connection) -> None:
    urls = [f"https://site.test/p{n}" for n in range(_PAGES)]
    ids = [
        record_seed(NormalizedUrl(url), is_internal=True, in_scope=True)(connection) for url in urls
    ]
    write_pages(connection, [_page(url_id, url) for url_id, url in zip(ids, urls, strict=True)])
    write_links(connection, [_link(url_id, urls[0]) for url_id in ids[1 : 1 + _SOURCES]])


def test_the_units_of_the_inlink_pass_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(_store_site)
        # The replay below then runs only the pass's units again.
        writer.flush()
        pages_200 = writer.run(pages_with_status_200)
        ranges = writer.run(inlink_ranges)
        for first, last in ranges:
            writer.run(inlink_counts(first, last, pages_200))
        replay_now(writer)

    assert (
        len(ranges),
        query(
            crawl.path,
            "SELECT inlinks, unique_inlinks, linking_pages_pct, count(*) FROM pages"
            " GROUP BY 1, 2, 3 ORDER BY 1",
        ),
    ) == (2, [(0, 0, 0.0, _PAGES - 1), (_SOURCES, _SOURCES, 0.08, 1)])
