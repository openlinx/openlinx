"""The Links of the HTTP Link and Refresh headers, and the refresh parser (020-add-crawl-core D5;
seam 4)."""

from datetime import UTC, datetime

import msgspec
import pytest
from hypothesis import given
from hypothesis import strategies as st
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.fetcher import FetchResult
from spider.crawl.headers import header_links
from spider.crawl.links import DiscoveredLink
from spider.crawl.pages import (
    Extractor,
    PageInput,
    PageSettings,
    PreparedPage,
    prepare_page,
    response_links,
)
from spider.crawl.refresh import refresh_url
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl, strip_params_pattern, url_host

SITE = NormalizedUrl("http://site.test/")


def _on_site(url: NormalizedUrl) -> bool:
    return url_host(url) == "site.test"


@pytest.mark.parametrize(
    ("content", "url"),
    [
        ("0; url=/new", "/new"),
        ("0;URL=/new", "/new"),
        ("5, url = /new", "/new"),
        ("0 url=/new", "/new"),
        ("0; /new", "/new"),
        ("0.5; url='/a b'c", "/a b"),
        ('  3; URL="/q?x=1"', "/q?x=1"),
        (".5;url=/a", "/a"),
        # HTML skips url and = only when url= is all there; a lookalike start is the URL.
        ("0; uploads/x", "uploads/x"),
        ("0; URLs/x", "URLs/x"),
        ("0; url-a", "url-a"),
        ("0; u", "u"),
        ("0; 'quoted'", "quoted"),
        ("0;\turl\t=\t/tab", "/tab"),
        ("0; url=", None),
        ("0", None),
        ("0;", None),
        ("; url=/new", None),
        ("x; url=/new", None),
        ("0x; url=/new", None),
        ("", None),
    ],
)
def test_a_refresh_names_its_target_as_html_reads_it(content: str, url: str | None) -> None:
    assert refresh_url(content) == url


@pytest.mark.parametrize(
    ("headers", "found"),
    [
        ([("Link", '</doc>; rel="canonical"')], [("canonical", "http://site.test/doc", ())]),
        (
            [("link", "<http://site.test/p2>; rel=next, </p0>;rel=prev")],
            [("pagination", "http://site.test/p2", ()), ("pagination", "http://site.test/p0", ())],
        ),
        (
            [("LINK", '</de/>; rel="alternate"; hreflang="de"')],
            [("hreflang", "http://site.test/de/", ())],
        ),
        ([("Link", '</feed>; rel="alternate"; type="application/rss+xml"')], []),
        ([("Link", "</s.css>; rel=preload; as=style")], []),
        (
            [("Link", '</a,b>; title="x, y"; rel="canonical nofollow"')],
            [("canonical", "http://site.test/a,b", ("nofollow",))],
        ),
        ([("Refresh", "5; url=/new")], [("http_refresh", "http://site.test/new", ())]),
        ([("Refresh", "5")], []),
        # RFC 8288: a parameter after the first of its name is ignored.
        ([("Link", "</c>; rel=canonical; rel=next")], [("canonical", "http://site.test/c", ())]),
        ([("Link", "garbage, <mailto:x@site.test>; rel=canonical")], []),
        # RFC 8288: an anchor makes the link-value describe another resource.
        (
            [("Link", '</b>; rel=canonical; anchor="/a", </c>; rel=canonical')],
            [("canonical", "http://site.test/c", ())],
        ),
        (
            [("Refresh", "0;url=/r"), ("X-Other", "<x>"), ("Link", "</c>; rel=canonical")],
            [("http_refresh", "http://site.test/r", ()), ("canonical", "http://site.test/c", ())],
        ),
    ],
)
def test_the_link_and_refresh_headers_give_links(
    headers: list[tuple[str, str]], found: list[tuple[str, str, tuple[str, ...]]]
) -> None:
    links = header_links(tuple(headers), SITE, is_internal=_on_site, strip_params=None)

    assert (
        [(link.type, link.target, tuple(t for t in link.rel if t == "nofollow")) for link in links],
        [(link.declared_in, link.ordinal) for link in links],
    ) == (found, [("http_header", n) for n in range(1, len(found) + 1)])


class _Seen(msgspec.Struct, frozen=True):
    links: tuple[DiscoveredLink, ...]


def _links_seen(tree: LexborHTMLParser, page: PageInput, config: None) -> _Seen:
    return _Seen(page.links)


def _seen(page: PreparedPage) -> tuple[DiscoveredLink, ...]:
    seen = dict(page.outputs)["seen"]
    assert isinstance(seen, _Seen)
    return seen.links


_PAGE_WITH_A_CANONICAL_HEADER = FetchResult(
    status_code=200,
    headers=(("Content-Type", "text/html"), ("Link", "</c>; rel=canonical")),
    body=b'<a href="/a">A</a>',
    fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
    response_time_ms=1,
)
_SEEING = PageSettings(
    scope=scope_rules(SITE), extractors=(Extractor("seen", _links_seen, None),), strip_params=None
)


def test_header_links_come_before_the_links_of_the_document() -> None:
    page = prepare_page(SITE, _PAGE_WITH_A_CANONICAL_HEADER, _SEEING)

    assert [(link.ordinal, link.declared_in, link.target) for link in _seen(page)] == [
        (1, "http_header", "http://site.test/c"),
        (2, "html", "http://site.test/a"),
    ]


def test_the_engine_finds_the_links_that_the_extractors_see() -> None:
    page = prepare_page(SITE, _PAGE_WITH_A_CANONICAL_HEADER, _SEEING)

    # As the engine joins them: its own header Links, then the prepared document's.
    joined = response_links(SITE, _PAGE_WITH_A_CANONICAL_HEADER, _SEEING.scope, None)
    assert joined + page.document_links == _seen(page)


_HEADER_PIECES = st.sampled_from(
    [
        "</a>",
        "<http://site.test/b>",
        "; rel=",
        '; rel="canonical"',
        "; rel=next",
        "; hreflang=",
        '; title="x, y"',
        '; anchor="/a"',
        ";",
        ",",
        "=",
        '"',
        "<",
        ">",
        "0; url=",
        " ",
        "\\",
    ]
)


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["Link", "Refresh", "link", "X-Other"]),
            st.lists(_HEADER_PIECES | st.text(max_size=6)).map("".join),
        )
    )
)
def test_the_header_links_accept_any_values(headers: list[tuple[str, str]]) -> None:
    links = header_links(tuple(headers), SITE, is_internal=_on_site, strip_params=None)

    assert isinstance(links, list)


def test_stripped_parameters_leave_every_link_of_a_page() -> None:
    response = FetchResult(
        status_code=200,
        headers=(("Content-Type", "text/html"), ("Link", "</c?utm_id=1>; rel=canonical")),
        body=b'<a href="/a?utm_id=2&x=1">A</a>',
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=1,
    )
    settings = PageSettings(scope=scope_rules(SITE), strip_params=strip_params_pattern(["utm_*"]))

    page = prepare_page(SITE, response, settings)

    assert [
        link.target
        for link in response_links(SITE, response, settings.scope, settings.strip_params)
        + page.document_links
    ] == ["http://site.test/c", "http://site.test/a?x=1"]
