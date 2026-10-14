"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5; seam 4)."""

from spider.crawl.discovery import discovered_urls
from spider.crawl.links import extract_links
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import NewUrl

SITE = NormalizedUrl("http://site.test/")


def test_a_page_records_each_url_it_links_to_once() -> None:
    body = (
        b'<a href="/a">A</a><img src="/logo.png"><a href="/b">B</a>'
        b'<a href="/a#top">A again</a><a href="http://other.test/">Other</a><a href="/b">B</a>'
    )
    links = extract_links(body, "text/html", SITE, is_internal=lambda url: True)

    assert discovered_urls(links, scope_rules(SITE), 1) == (
        NewUrl(
            url=NormalizedUrl("http://site.test/a"),
            crawl_depth=1,
            discovered_via="hyperlink",
            is_internal=True,
            in_scope=True,
        ),
        NewUrl(
            url=NormalizedUrl("http://site.test/b"),
            crawl_depth=1,
            discovered_via="hyperlink",
            is_internal=True,
            in_scope=True,
        ),
        NewUrl(
            url=NormalizedUrl("http://other.test/"),
            crawl_depth=1,
            discovered_via="hyperlink",
            is_internal=False,
            in_scope=False,
        ),
    )
