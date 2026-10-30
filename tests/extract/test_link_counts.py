"""Inlink and outlink counts (030-add-page-data, page-data; seam 3+6)."""

from dataclasses import replace
from pathlib import Path

from sqlalchemy import Connection, select

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.services.hooks import default_hooks
from openlinx.store.crawls import crawl_summary
from openlinx.store.schema import pages
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

_COUNTS_OF = (
    "SELECT inlinks, unique_inlinks, linking_pages_pct, outlinks, unique_outlinks,"
    " external_outlinks, unique_external_outlinks FROM pages WHERE address = ?"
)


def _linked_site(fixture_hosts: StartHosts) -> Path:
    # The spec's site. D is reached only through a pagination Link, which no count reads, and
    # one of A's Links to B is nofollow, which still counts.
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(
                    body='<html><head><link rel="next" href="/d"></head><body>'
                    '<a href="/b">B</a> <a href="/b" rel="nofollow">More about B</a>'
                    ' <a href="/c">C</a>'
                    ' <a href="/">Home</a> <a href="http://other.test/e1">E1</a>'
                    ' <a href="http://other.test/e1">E1 again</a>'
                    ' <a href="http://other.test/e2">E2</a></body></html>'
                ),
                "/b": Page(body='<a href="/">A</a>'),
                "/c": Page(body='<a href="/">A</a>'),
                "/d": Page(body='<a href="/">A</a>'),
            }
        ),
        Site(routes={"/e1": Page(body="<p>E1</p>"), "/e2": Page(body="<p>E2</p>")}),
    )
    return crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file


def test_counts_for_a_linked_page(temp_workspace: TempWorkspace, fixture_hosts: StartHosts) -> None:
    crawl_file = _linked_site(fixture_hosts)

    assert query(crawl_file, _COUNTS_OF, ["http://site.test/"]) == [(3, 3, 75.0, 3, 2, 3, 2)]


def test_repeated_inlinks_from_one_source(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    crawl_file = _linked_site(fixture_hosts)

    assert [
        query(crawl_file, _COUNTS_OF, [f"http://site.test{path}"])[0][:3] for path in ("/b", "/d")
    ] == [(2, 1, 25.0), (0, 0, 0.0)]


def _stored_inlinks(connection: Connection) -> list[int | None]:
    return list(connection.execute(select(pages.c.inlinks)).scalars())


def test_inlinks_are_null_while_the_crawl_runs(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/a">A</a>'), "/a": Page(body='<a href="/">Home</a>')})
    )
    seen: list[tuple[str, list[int | None]]] = []

    async def record_inlinks(context: PassContext) -> None:
        state = (await context.writer.run_async(crawl_summary())).state
        seen.append((state, await context.writer.run_async(_stored_inlinks)))

    defaults = default_hooks()
    # The passes run before the Crawl's end is written, so a pass ahead of the inlink pass
    # sees the Crawl running with every Page stored.
    hooks = replace(defaults, passes=(Pass("record_inlinks", record_inlinks), *defaults.passes))

    crawl_result(server.url("/"), hooks)

    assert seen == [("running", [None, None])]


def test_linking_pages_pct_is_rounded_half_up(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A hub that links to 31 Pages: each is linked from 1 of the 32, exactly 3.125 %.
    routes = {f"/p{n}": Page(body=f"<p>Page {n}</p>") for n in range(1, 32)}
    hub = "".join(f'<a href="/p{n}">Page {n}</a>' for n in range(1, 32))
    server = fixture_site(Site(routes={"/": Page(body=hub), **routes}))

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(
        crawl_file,
        "SELECT DISTINCT linking_pages_pct FROM pages WHERE address <> ?",
        [server.url("/")],
    ) == [(3.13,)]


def test_linking_pages_pct_is_null_without_a_page_with_status_200(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Status(404, body="<p>Gone</p>")}))

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(crawl_file, _COUNTS_OF, [server.url("/")]) == [
        (0, 0, None, None, None, None, None)
    ]
