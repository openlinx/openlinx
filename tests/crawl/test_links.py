"""Link discovery in HTML (020-add-crawl-core, crawling)."""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.fetcher import FetchResult
from spider.crawl.links import DiscoveredLink, extract_links, header_links, refresh_url
from spider.crawl.pages import PageSettings, prepare_page
from spider.crawl.scope import scope_rules
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
        (
            '<video><track src="/t.vtt" srcset="/x.png 1x"></video>',
            ("video", "track", "src", "http://site.test/t.vtt"),
        ),
        ('<a href="">Here</a>', ("hyperlink", "a", "href", "http://site.test/")),
    ],
)
def test_each_element_gives_its_link_type(html: str, expected: tuple[str, ...]) -> None:
    found = [(link.type, link.element, link.attribute, link.target) for link in _links(html)]

    assert found == [expected]


@pytest.mark.parametrize(
    "html",
    [
        '<base href="javascript:void(0)"><a href="guide">Guide</a>',
        '<a href="//">x</a>',
        '<img src="">',
        '<script src=" "></script>',
        '<embed src="">',
        '<object data=""></object>',
        '<video poster=""></video>',
        '<link rel="stylesheet" href="">',
    ],
)
def test_references_that_name_no_file_give_no_link(html: str) -> None:
    assert _links(html) == []


def test_rel_tokens_are_lower_cased_and_nofollow_is_read_from_them() -> None:
    links = _links('<a rel=" NoFollow\tUGC " href="/x">x</a><a href="/y">y</a>')

    assert [(link.rel, link.nofollow) for link in links] == [
        (("nofollow", "ugc"), True),
        ((), False),
    ]


def test_references_that_are_not_http_or_https_are_ignored() -> None:
    links = _links('<a href="mailto:hi@site.test">Mail</a><a href="javascript:void(0)">Menu</a>')

    assert links == []


def test_a_malformed_reference_is_ignored() -> None:
    found = _found('<a href="http://[bad/x">Bad</a><a href="/ok">OK</a>')

    assert found == [("hyperlink", "http://site.test/ok")]


def test_links_are_read_from_the_decoded_document() -> None:
    body = '<a href="/й">x</a>'.encode("cp1251")

    links = extract_links(body, "text/html; charset=windows-1251", SITE, is_internal=_on_site)

    assert [link.target for link in links] == ["http://site.test/%D0%B9"]


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("\\catalog", ["http://site.test/catalog"]),
        ("/a\\b?x\\y", ["http://site.test/a/b?x%5Cy"]),
        ("\\\\cdn.test\\i.png", ["http://cdn.test/i.png"]),
        ("///cdn.test/x", ["http://cdn.test/x"]),
        ("/\\cdn.test/x", ["http://cdn.test/x"]),
        ("http:\\\\cdn.test\\x", ["http://cdn.test/x"]),
        ("https:cdn.test/x", ["https://cdn.test/x"]),
        ("https:///cdn.test/x", ["https://cdn.test/x"]),
        ("http:p", ["http://site.test/p"]),
        ("http:", ["http://site.test/"]),
        ("&#11; /a&#9;/b&#10; &#1;", ["http://site.test/a/b"]),
        ("//", []),
        ("//?q", []),
        ("\\\\", []),
        ("https:", []),
    ],
)
def test_references_resolve_as_browsers_resolve_them(href: str, expected: list[str]) -> None:
    found = [link.target for link in _links(f'<a href="{href}">x</a>')]

    assert found == expected


@pytest.mark.parametrize(
    ("html", "charset", "expected"),
    [
        ('<a href="/s?q=й">', "windows-1251", "http://site.test/s?q=%E9"),
        ('<a href="/й?q=й#й">', "windows-1251", "http://site.test/%D0%B9?q=%E9"),
        ('<a href="/s?q=ж✓">', "windows-1251", "http://site.test/s?q=%E6&%2310003;"),
        ('<base href="/b/?q=й"><a href="">', "windows-1251", "http://site.test/b/?q=%E9"),
        ('<a href="/s?q=й">', "utf-8", "http://site.test/s?q=%D0%B9"),
        ('<a href="/s?q=й">', "utf-16le", "http://site.test/s?q=%D0%B9"),
    ],
)
def test_queries_are_encoded_in_the_page_encoding(html: str, charset: str, expected: str) -> None:
    body = html.encode(charset, "xmlcharrefreplace")

    links = extract_links(body, f"text/html; charset={charset}", SITE, is_internal=_on_site)

    assert [link.target for link in links] == [expected]


_FRAGMENTS = st.sampled_from(
    [
        "<a href=",
        "<area href='",
        "<base href=",
        '<img src="/i" srcset="',
        "<link rel=",
        "<video>",
        "<audio>",
        "<source src=",
        "<track src=",
        "<object data=",
        "<meta charset=",
        "<!--",
        "<script>",
        "</",
        ">",
        '"',
        "'",
        " 1x, ",
        "(",
        ")",
        ",",
        "http://[",
        '<a href="http://[bad/x">',
        '<img srcset="http://[ 1x, //[::1 2x">',
        "//",
        "\\",
        "///",
        "http:\\\\",
        "https:",
        "?q=",
        "#",
        "&amp;",
        "&#11;",
        "\x00",
    ]
)
_MALFORMED_HTML = st.lists(_FRAGMENTS | st.text(max_size=8)).map("".join)
_ENCODINGS = st.sampled_from(["utf-8", "windows-1251", "shift_jis", "iso-2022-jp", "utf-16le"])
_BODIES = (
    st.binary()
    | _MALFORMED_HTML.map(lambda html: html.encode("utf-8", "surrogatepass"))
    | st.builds(lambda html, codec: html.encode(codec, "replace"), _MALFORMED_HTML, _ENCODINGS)
)
_CONTENT_TYPES = (
    st.none()
    | st.text()
    | st.text().map("text/html; charset={}".format)
    | _ENCODINGS.map("text/html; charset={}".format)
)


@given(_BODIES, _CONTENT_TYPES)
def test_the_link_extractor_accepts_any_bytes(body: bytes, content_type: str | None) -> None:
    links = extract_links(body, content_type, SITE, is_internal=_on_site)

    assert isinstance(links, list)


def test_deeply_nested_html_gives_its_links() -> None:
    depth = 100_000

    found = _found("<span>" * depth + '<a href="/after">x</a>' + "</span>" * depth)

    assert found == [("hyperlink", "http://site.test/after")]


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
        ([("Link", "garbage, <mailto:x@site.test>; rel=canonical")], []),
        (
            [("Refresh", "0;url=/r"), ("X-Other", "<x>"), ("Link", "</c>; rel=canonical")],
            [("http_refresh", "http://site.test/r", ()), ("canonical", "http://site.test/c", ())],
        ),
    ],
)
def test_the_link_and_refresh_headers_give_links(
    headers: list[tuple[str, str]], found: list[tuple[str, str, tuple[str, ...]]]
) -> None:
    links = header_links(tuple(headers), SITE, is_internal=_on_site)

    assert (
        [(link.type, link.target, tuple(t for t in link.rel if t == "nofollow")) for link in links],
        [(link.declared_in, link.ordinal) for link in links],
    ) == (found, [("http_header", n) for n in range(1, len(found) + 1)])


def test_header_links_come_before_the_links_of_the_document() -> None:
    response = FetchResult(
        status_code=200,
        headers=(("Content-Type", "text/html"), ("Link", "</c>; rel=canonical")),
        body=b'<a href="/a">A</a>',
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=1,
    )

    page = prepare_page(SITE, response, PageSettings(scope=scope_rules(SITE)))

    assert [(link.ordinal, link.declared_in, link.target) for link in page.links] == [
        (1, "http_header", "http://site.test/c"),
        (2, "html", "http://site.test/a"),
    ]


_HEADER_PIECES = st.sampled_from(
    [
        "</a>",
        "<http://site.test/b>",
        "; rel=",
        '; rel="canonical"',
        "; rel=next",
        "; hreflang=",
        '; title="x, y"',
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
    assert isinstance(header_links(tuple(headers), SITE, is_internal=_on_site), list)
