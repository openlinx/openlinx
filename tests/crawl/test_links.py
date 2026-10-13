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


def _found(html: str, url: NormalizedUrl = SITE) -> list[tuple[str, str]]:
    return [(link.type, link.target) for link in _links(html, url)]


def test_every_srcset_candidate_is_an_image_link() -> None:
    found = _found('<img src="/a.png" srcset="/a-2x.png 2x, /a-3x.png 3x">')

    assert found == [
        ("image", "http://site.test/a.png"),
        ("image", "http://site.test/a-2x.png"),
        ("image", "http://site.test/a-3x.png"),
    ]


def test_video_and_audio_sources_are_video_and_audio_links() -> None:
    found = _found(
        '<video src="/v.mp4"><track src="/v.vtt"></video><audio><source src="/a.mp3"></audio>'
    )

    assert found == [
        ("video", "http://site.test/v.mp4"),
        ("video", "http://site.test/v.vtt"),
        ("audio", "http://site.test/a.mp3"),
    ]
