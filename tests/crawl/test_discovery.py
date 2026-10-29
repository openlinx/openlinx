"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5; seam 4)."""

import pytest

from openlinx.crawl.engine.discovery import discovered_urls
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import NewUrl
from tests.support.pages import page_links

SITE = NormalizedUrl("http://site.test/")


def test_a_page_records_each_url_it_links_to_once() -> None:
    body = (
        b'<a href="/a">A</a><img src="/logo.png"><a href="/b">B</a>'
        b'<a href="/a#top">A again</a><a href="http://other.test/">Other</a><a href="/b">B</a>'
    )
    links = page_links(body, "text/html", SITE)

    assert discovered_urls(links, scope_rules(SITE)) == (
        NewUrl(
            url=NormalizedUrl("http://site.test/a"),
            discovered_via="hyperlink",
            is_internal=True,
            in_scope=True,
        ),
        NewUrl(
            url=NormalizedUrl("http://site.test/logo.png"),
            discovered_via="image",
            is_internal=True,
            in_scope=True,
        ),
        NewUrl(
            url=NormalizedUrl("http://site.test/b"),
            discovered_via="hyperlink",
            is_internal=True,
            in_scope=True,
        ),
        NewUrl(
            url=NormalizedUrl("http://other.test/"),
            discovered_via="hyperlink",
            is_internal=False,
            in_scope=False,
        ),
    )


def _recorded(html: str) -> list[tuple[str, str, str | None]]:
    links = page_links(html.encode(), "text/html", SITE)
    return [
        (new.url, new.discovered_via, new.skip_reason)
        for new in discovered_urls(links, scope_rules(SITE))
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
        ('<link rel="canonical" href="/c">', [("http://site.test/c", "canonical", None)]),
        (
            '<a href="/x.png">X</a><img src="/x.png">',
            [("http://site.test/x.png", "image", None)],
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
        (
            '<img src="/i.png"><link rel="stylesheet" href="/s.css">',
            [("http://site.test/i.png", "image", None), ("http://site.test/s.css", "css", None)],
        ),
        (
            '<script src="/s.js"></script><embed src="/e.swf">',
            [
                ("http://site.test/s.js", "javascript", None),
                ("http://site.test/e.swf", "media", None),
            ],
        ),
        (
            '<link rel="icon" href="/x"><img src="/y"><a href="/x">X</a><a href="/y">Y</a>',
            [("http://site.test/x", "hyperlink", None), ("http://site.test/y", "image", None)],
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


def _page_nofollow(follow_nofollow: bool) -> tuple[NewUrl, ...]:
    # A page-level nofollow, as a staging Page's robots meta gives it.
    body = (
        b'<meta name="robots" content="nofollow"><a rel="nofollow" href="/n">N</a>'
        b'<a href="/x">X</a><link rel="icon" href="/i">'
    )
    links = page_links(body, "text/html", SITE, follow_nofollow=follow_nofollow)
    return discovered_urls(links, scope_rules(SITE))


def test_follow_nofollow_follows_every_nofollow_hyperlink_and_only_those() -> None:
    honoured = _page_nofollow(follow_nofollow=False)
    followed = _page_nofollow(follow_nofollow=True)

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
