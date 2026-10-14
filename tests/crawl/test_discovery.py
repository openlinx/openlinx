"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5; seam 4)."""

import pytest

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


def _recorded(html: str) -> list[tuple[str, str, str | None]]:
    links = extract_links(html.encode(), "text/html", SITE, is_internal=lambda url: True)
    return [
        (new.url, new.discovered_via, new.skip_reason)
        for new in discovered_urls(links, scope_rules(SITE), 1)
    ]


@pytest.mark.parametrize(
    ("html", "recorded"),
    [
        ('<a href="/a">A</a>', [("http://site.test/a", "hyperlink", None)]),
        ('<map><area href="/m"></map>', [("http://site.test/m", "hyperlink", None)]),
        ('<link rel="next" href="/p2">', [("http://site.test/p2", "pagination", None)]),
        (
            '<link rel="alternate" hreflang="de" href="/de/">',
            [("http://site.test/de/", "hreflang", None)],
        ),
        ('<iframe src="/f"></iframe>', [("http://site.test/f", "iframe", None)]),
        (
            '<meta http-equiv="refresh" content="0; url=/new">',
            [("http://site.test/new", "meta_refresh", None)],
        ),
        (
            '<link rel="amphtml" href="/amp/">',
            [("http://site.test/amp/", "amphtml", "link_type_not_followed")],
        ),
        (
            '<link rel="alternate" media="handheld" href="/m/">',
            [("http://site.test/m/", "mobile_alternate", "link_type_not_followed")],
        ),
        (
            '<link rel="icon" href="/favicon.ico">',
            [("http://site.test/favicon.ico", "misc", "link_type_not_followed")],
        ),
        ('<img src="/i.png"><link rel="stylesheet" href="/s.css">', []),
        ('<script src="/s.js"></script><embed src="/e.swf">', []),
        (
            '<link rel="icon" href="/x"><img src="/y"><a href="/x">X</a><a href="/y">Y</a>',
            [("http://site.test/x", "hyperlink", None), ("http://site.test/y", "hyperlink", None)],
        ),
        (
            '<a rel="nofollow" href="/n">N</a>',
            [("http://site.test/n", "hyperlink", "nofollow")],
        ),
        (
            '<a rel="nofollow" href="/x">X</a><a href="/x">X</a>',
            [("http://site.test/x", "hyperlink", None)],
        ),
        (
            '<a href="/x">X</a><link rel="amphtml" href="/x">',
            [("http://site.test/x", "hyperlink", None)],
        ),
    ],
)
def test_each_link_type_is_followed_or_recorded_as_not_followed(
    html: str, recorded: list[tuple[str, str, str | None]]
) -> None:
    assert _recorded(html) == recorded


def test_follow_nofollow_follows_every_nofollow_hyperlink_and_only_those() -> None:
    body = b'<a rel="nofollow" href="/n">N</a><a href="/x">X</a><link rel="icon" href="/i">'
    links = extract_links(body, "text/html", SITE, is_internal=lambda url: True)
    scope = scope_rules(SITE)

    honoured = discovered_urls(links, scope, 1, nofollow=True)
    followed = discovered_urls(links, scope, 1, nofollow=True, follow_nofollow=True)

    assert (
        [(new.url, new.skip_reason) for new in honoured],
        [(new.url, new.skip_reason) for new in followed],
    ) == (
        [
            ("http://site.test/n", "nofollow"),
            ("http://site.test/x", "nofollow"),
            ("http://site.test/i", "link_type_not_followed"),
        ],
        [
            ("http://site.test/n", None),
            ("http://site.test/x", None),
            ("http://site.test/i", "link_type_not_followed"),
        ],
    )
