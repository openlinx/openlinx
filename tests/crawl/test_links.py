"""Link discovery in HTML (020-add-crawl-core, crawling)."""

import pytest

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


def test_rel_previous_is_a_pagination_link() -> None:
    found = _found('<link rel="previous" href="/p1">', NormalizedUrl("http://site.test/p2"))

    assert found == [("pagination", "http://site.test/p1")]


def test_a_link_element_of_another_rel_is_a_misc_link() -> None:
    found = _found(
        '<link rel="icon" href="/favicon.ico"><link rel="preconnect" href="https://cdn.site.test">'
    )

    assert found == [("misc", "http://site.test/favicon.ico")]


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<area href="/m">', ("hyperlink", "area", "href", "http://site.test/m")),
        ('<link rel="next" href="/p3">', ("pagination", "link", "href", "http://site.test/p3")),
        ('<link rel="prev" href="/p1">', ("pagination", "link", "href", "http://site.test/p1")),
        (
            '<link rel="alternate" hreflang="de" href="/de/">',
            ("hreflang", "link", "href", "http://site.test/de/"),
        ),
        (
            '<link rel="alternate" media="only screen and (max-width: 640px)" href="/m/">',
            ("mobile_alternate", "link", "href", "http://site.test/m/"),
        ),
        (
            '<link rel="alternate" type="application/rss+xml" href="/feed">',
            ("misc", "link", "href", "http://site.test/feed"),
        ),
        (
            '<link rel="Alternate StyleSheet" href="/s.css">',
            ("css", "link", "href", "http://site.test/s.css"),
        ),
        ('<iframe src="/f"></iframe>', ("iframe", "iframe", "src", "http://site.test/f")),
        (
            '<frameset><frame src="/f"></frameset>',
            ("iframe", "frame", "src", "http://site.test/f"),
        ),
        ('<script src="/s.js"></script>', ("javascript", "script", "src", "http://site.test/s.js")),
        ('<embed src="/e.swf">', ("media", "embed", "src", "http://site.test/e.swf")),
        ('<object data="/o.bin"></object>', ("media", "object", "data", "http://site.test/o.bin")),
        ('<video poster="/p.png"></video>', ("image", "video", "poster", "http://site.test/p.png")),
        (
            '<picture><source srcset="/w.webp 1x"></picture>',
            ("image", "source", "srcset", "http://site.test/w.webp"),
        ),
    ],
)
def test_each_element_gives_its_link_type(html: str, expected: tuple[str, ...]) -> None:
    found = [(link.type, link.element, link.attribute, link.target) for link in _links(html)]

    assert found == [expected]


def test_rel_tokens_are_lower_cased_and_nofollow_is_read_from_them() -> None:
    links = _links('<a rel=" NoFollow\tUGC " href="/x">x</a><a href="/y">y</a>')

    assert [(link.rel, link.nofollow) for link in links] == [
        (("nofollow", "ugc"), True),
        ((), False),
    ]
