"""Stored Links match discovery (030-add-page-data, page-data; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_discovered_urls_are_the_stored_link_targets(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/links": Page(
                    body='<a href="/a">a</a><a href="/b" rel="nofollow">b</a><img src="/i.png">'
                ),
                "/a": Page(body="<p>A</p>"),
                "/b": Page(body="<p>B</p>"),
                "/i.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawl_result(server.url("/links")).crawl_file

    targets = [server.url("/a"), server.url("/b"), server.url("/i.png")]
    assert sorted(url for (url,) in query(crawl_file, "SELECT url FROM urls")) == sorted(
        [server.url("/links"), *targets]
    )
    assert query(
        crawl_file,
        "SELECT target.url FROM links JOIN urls AS target ON target.id = links.target_url_id"
        " ORDER BY links.ordinal",
    ) == [(target,) for target in targets]


def test_a_pdf_stores_the_links_of_its_headers(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/guide.pdf": Page(
                    body="%PDF-1.7",
                    content_type="application/pdf",
                    headers=(
                        (
                            "Link",
                            '</guide>; rel="canonical", </de/guide.pdf>; rel="alternate"; '
                            'hreflang="de"',
                        ),
                    ),
                ),
                "/guide": Page(body="<p>Guide</p>"),
                "/de/guide.pdf": Page(body="%PDF-1.7", content_type="application/pdf"),
            }
        )
    )

    crawl_file = crawl_result(server.url("/guide.pdf")).crawl_file

    assert query(
        crawl_file,
        "SELECT target.url, links.type, links.declared_in, links.hreflang FROM links"
        " JOIN urls AS source ON source.id = links.source_url_id"
        " JOIN urls AS target ON target.id = links.target_url_id WHERE source.url = ?"
        " ORDER BY links.ordinal",
        [server.url("/guide.pdf")],
    ) == [
        (server.url("/guide"), "canonical", "http_header", None),
        (server.url("/de/guide.pdf"), "hreflang", "http_header", "de"),
    ]
