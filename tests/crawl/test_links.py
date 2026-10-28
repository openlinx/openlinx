"""Link discovery in HTML (020-add-crawl-core, crawling)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.references import DiscoveredLink
from spider.crawl.urls import NormalizedUrl
from tests.support.pages import page_links

SITE = NormalizedUrl("http://site.test/")


def _links(html: str, url: NormalizedUrl = SITE) -> list[DiscoveredLink]:
    return list(page_links(html.encode(), "text/html", url))


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
            skip_reason=None,
            declared_in="body",
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
            '<link rel="canonical" href="/c">',
            ("canonical", "link", "href", "http://site.test/c"),
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

    links = page_links(body, "text/html; charset=windows-1251", SITE)

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

    links = page_links(body, f"text/html; charset={charset}", SITE)

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
    links = page_links(body, content_type, SITE)

    assert isinstance(links, tuple)


def test_deeply_nested_html_gives_its_links() -> None:
    depth = 100_000

    found = _found("<span>" * depth + '<a href="/after">x</a>' + "</span>" * depth)

    assert found == [("hyperlink", "http://site.test/after")]


@pytest.mark.parametrize(
    ("html", "found"),
    [
        ('<head><link rel="icon" href="/i.ico"></head>', [("misc", "http://site.test/i.ico")]),
        ('<head><noscript><link rel="icon" href="/i.ico"></noscript></head>', []),
        ('<head><noscript><link rel="canonical" href="/c"></noscript></head>', []),
        (
            '<head><noscript><meta http-equiv="refresh" content="0; url=/no-js"></noscript></head>',
            [],
        ),
        # The user's decision: a crawler without rendering finds every URL the raw HTML holds.
        (
            '<body><noscript><a href="/a">A</a><img src="/pixel.gif"></noscript></body>',
            [("hyperlink", "http://site.test/a"), ("image", "http://site.test/pixel.gif")],
        ),
        (
            '<a href="/1"></a><noscript><a href="/2"></a><link rel="icon" href="/i.ico">'
            '<img src="/3"></noscript><a href="/4"></a>',
            [
                ("hyperlink", "http://site.test/1"),
                ("hyperlink", "http://site.test/2"),
                ("image", "http://site.test/3"),
                ("hyperlink", "http://site.test/4"),
            ],
        ),
        (
            '<head><noscript><img src="/px.gif"></noscript><link rel="icon" href="/i.ico"></head>',
            [("image", "http://site.test/px.gif"), ("misc", "http://site.test/i.ico")],
        ),
        (
            '<head><noscript><base href="/other/"></noscript></head><a href="a"></a>',
            [("hyperlink", "http://site.test/a")],
        ),
        # A page's own template holds placeholders that scripts fill in (design D5).
        ('<template><a href="{{ url }}"></a></template>', []),
        # With scripting on, the content of a <script> is text.
        ('<script>"<noscript>"</script><a href="/x"></a>', [("hyperlink", "http://site.test/x")]),
        # The content of a <noscript> is text, so a comment there hides no end tag.
        (
            '<noscript><!-- </noscript> --><a href="/kept"></a>',
            [("hyperlink", "http://site.test/kept")],
        ),
        (
            '<noscript><a href="/a"></a><noscript></noscript><a href="/c"></a></noscript>',
            [("hyperlink", "http://site.test/a"), ("hyperlink", "http://site.test/c")],
        ),
        # A foreign <noscript>'s child elements give their Links once; its text is decoded markup.
        (
            '<svg><noscript><a href="/x"></a></noscript></svg>',
            [("hyperlink", "http://site.test/x")],
        ),
        (
            '<math display="block"><mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup>'
            '<noscript><a href="/formula">The formula</a></noscript></math>',
            [("hyperlink", "http://site.test/formula")],
        ),
        (
            '<svg viewBox="0 0 10 10"><noscript><link rel="canonical" href="/c"></noscript></svg>',
            [],
        ),
        # At an HTML integration point a <noscript> is HTML, and its text gives its Links once.
        (
            '<button><svg viewBox="0 0 24 24" aria-labelledby="t"><title id="t">Cart<noscript>'
            '<a href="/cart">Open the cart</a></noscript></title><path d="M7 18h10"/></svg>'
            "</button>",
            [("hyperlink", "http://site.test/cart")],
        ),
        (
            '<svg role="img" viewBox="0 0 100 50"><desc>Sales by month<noscript>'
            '<a href="/sales.csv">Download the data</a></noscript></desc>'
            '<rect width="40" height="50"/></svg>',
            [("hyperlink", "http://site.test/sales.csv")],
        ),
        (
            '<svg width="200" height="100"><foreignObject width="200" height="100"><div>'
            '<noscript><a href="/more">Read more</a></noscript></div></foreignObject></svg>',
            [("hyperlink", "http://site.test/more")],
        ),
        (
            '<p>The ratio <math><mi>&pi;<noscript><a href="/pi">pi</a></noscript></mi></math></p>',
            [("hyperlink", "http://site.test/pi")],
        ),
        (
            '<math><semantics><mi>x</mi><annotation-xml encoding="text/html"><noscript>'
            '<a href="/x">x</a></noscript></annotation-xml></semantics></math>',
            [("hyperlink", "http://site.test/x")],
        ),
        ('<svg><noscript>&lt;a href="/y"&gt;</noscript></svg>', []),
        ('<math><noscript>&lt;a href="/y"&gt;</noscript></math>', []),
        (
            '<NoScript class="a"><a href="/x"></a></NOSCRIPT >',
            [("hyperlink", "http://site.test/x")],
        ),
        ('<p></p><noscript><a href="/open">', [("hyperlink", "http://site.test/open")]),
        (
            '<template></noscript></template><a href="/t"></a>',
            [("hyperlink", "http://site.test/t")],
        ),
    ],
)
def test_noscript_hides_head_metadata_but_not_the_links_of_the_body(
    html: str, found: list[tuple[str, str]]
) -> None:
    assert _found(html) == found
