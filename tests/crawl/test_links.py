"""Link discovery in HTML (020-add-crawl-core, crawling)."""

from spider.crawl.links import DiscoveredLink, extract_links
from spider.crawl.urls import NormalizedUrl, url_host

SITE = NormalizedUrl("http://site.test/")


def _on_site(url: NormalizedUrl) -> bool:
    return url_host(url) == "site.test"


def _links(html: str, url: NormalizedUrl = SITE) -> list[DiscoveredLink]:
    return extract_links(html.encode(), "text/html", url, is_internal=_on_site)


def test_a_relative_link_is_resolved_against_the_base_href() -> None:
    links = _links('<base href="http://site.test/docs/"><a href="guide">Guide</a>')

    assert links == [
        DiscoveredLink(
            type="hyperlink",
            target=NormalizedUrl("http://site.test/docs/guide"),
            raw="guide",
            element="a",
            attribute="href",
            rel=(),
            nofollow=False,
            declared_in="html",
            ordinal=1,
            is_internal=True,
        )
    ]
