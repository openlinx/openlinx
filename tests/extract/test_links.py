"""Link attributes and source pairs agree with their declarations (030 D4; 023 D12; seam 4)."""

from openlinx.store.records import LINK_TYPES, LinkAttribute, LinkElement, LinkType
from openlinx.store.schema import literal_values
from tests.support.page_data import page_link_rows, response_link_rows


def test_header_and_repeated_html_links_keep_their_ordinals_and_positions() -> None:
    rows = page_link_rows(
        '<nav><a href="/same">Nav</a></nav><main><a href="/same">Main</a></main>',
        headers=(("Link", '</c>; rel="canonical"'),),
    )

    assert [(row.ordinal, row.anchor_text, row.link_position) for row in rows] == [
        (1, None, None),
        (2, "Nav", "navigation"),
        (3, "Main", "content"),
    ]


def test_hyperlink_with_rel_flags() -> None:
    (row,) = page_link_rows(
        '<main><a href="/b" rel="nofollow UGC">Read  more</a></main>', url="https://example.test/a"
    )

    assert (
        row.type,
        row.target,
        row.anchor_text,
        row.rel,
        row.rel_nofollow,
        row.rel_ugc,
        row.rel_sponsored,
        row.declared_in,
        row.link_position,
    ) == (
        "hyperlink",
        "https://example.test/b",
        "Read more",
        "nofollow ugc",
        True,
        True,
        False,
        "body",
        "content",
    )


def test_followed_is_the_crawls_follow_rule() -> None:
    page = page_link_rows(
        '<html><head><link rel="amphtml" href="/a.amp"></head><body>'
        '<a href="/a" rel="nofollow">A</a><a href="/b">B</a><img src="/i.png" alt=""></body></html>'
    )
    # The Page's own nofollow stops a hyperlink whose rel says nothing.
    nofollow_page = page_link_rows(
        '<html><head><meta name="robots" content="nofollow"></head>'
        '<body><a href="/c">C</a></body></html>'
    )

    assert [(row.type, row.rel_nofollow, row.followed) for row in page + nofollow_page] == [
        ("amphtml", False, False),
        ("hyperlink", True, False),
        ("hyperlink", False, True),
        ("image", False, True),
        ("hyperlink", False, False),
    ]


def test_image_alt_attribute_absent_or_empty() -> None:
    rows = page_link_rows('<img src="/a.png"><img src="/b.png" alt="">')

    assert [(row.type, row.target, row.element, row.attribute, row.alt_text) for row in rows] == [
        ("image", "https://site.test/a.png", "img", "src", None),
        ("image", "https://site.test/b.png", "img", "src", ""),
    ]


def test_image_only_anchor_takes_the_alt_text() -> None:
    (link, _) = page_link_rows('<a href="/c"><img src="/i.png" alt="Logo"></a>')

    assert (link.type, link.target, link.anchor_text) == (
        "hyperlink",
        "https://site.test/c",
        "Logo",
    )


def test_an_image_map_area_takes_its_alt_text() -> None:
    rows = page_link_rows(
        '<img src="/map.png" usemap="#m"><map name="m">'
        '<area shape="rect" coords="0,0,50,50" href="/north" alt="North  office">'
        '<area shape="rect" coords="50,0,100,50" href="/south"></map>'
    )

    assert [(row.target, row.anchor_text) for row in rows if row.type == "hyperlink"] == [
        ("https://site.test/north", "North office"),
        ("https://site.test/south", ""),
    ]


def test_every_occurrence_is_stored() -> None:
    rows = page_link_rows('<a href="/b">1</a><a href="/b">2</a>')

    assert [(row.type, row.target, row.anchor_text) for row in rows] == [
        ("hyperlink", "https://site.test/b", "1"),
        ("hyperlink", "https://site.test/b", "2"),
    ]


def test_link_positions_come_from_the_enclosing_element() -> None:
    rows = page_link_rows(
        '<head><link rel="canonical" href="/x"></head><body><header><a href="/h">H</a></header>'
        '<nav><a href="/n">N</a></nav><main><a href="/c">C</a></main><aside><a href="/s">S</a>'
        '</aside><footer><nav><a href="/f">F</a></nav><noscript><img src="/pixel.gif">'
        "</noscript></footer></body>"
    )

    assert [(row.type, row.target, row.link_position) for row in rows] == [
        ("canonical", "https://site.test/x", "head"),
        ("hyperlink", "https://site.test/h", "header"),
        ("hyperlink", "https://site.test/n", "navigation"),
        ("hyperlink", "https://site.test/c", "content"),
        ("hyperlink", "https://site.test/s", "sidebar"),
        ("hyperlink", "https://site.test/f", "navigation"),
        ("image", "https://site.test/pixel.gif", "footer"),
    ]


def test_hreflang_and_mobile_alternate_links() -> None:
    rows = page_link_rows(
        '<head><link rel="alternate" hreflang="de" href="/de/">'
        '<link rel="alternate" media="only screen and (max-width: 640px)" '
        'href="https://m.example.test/"></head>'
    )

    assert [(row.type, row.hreflang, row.media) for row in rows] == [
        ("hreflang", "de", None),
        ("mobile_alternate", None, "only screen and (max-width: 640px)"),
    ]


def test_links_declared_in_a_header() -> None:
    (link,) = page_link_rows(
        "<p>Page two</p>", headers=(("Link", '</p3>; rel="next"'),), url="https://example.test/p2"
    )

    assert (
        link.type,
        link.target,
        link.ordinal,
        link.declared_in,
        link.element,
        link.attribute,
        link.link_position,
    ) == ("pagination", "https://example.test/p3", 1, "http_header", None, None, None)


def test_hreflang_from_a_link_header() -> None:
    (link,) = response_link_rows(
        "application/pdf",
        headers=(("Link", '<https://example.test/de/guide.pdf>; rel="alternate"; hreflang="de"'),),
        url="https://example.test/guide.pdf",
    )

    assert (
        link.type,
        link.target,
        link.hreflang,
        link.declared_in,
        link.element,
        link.link_position,
    ) == ("hreflang", "https://example.test/de/guide.pdf", "de", "http_header", None, None)


# Every element and attribute that Link discovery reads, as real pages write them: a frame
# only in a frameset document, a source in a picture and in a video, a track in a video and an
# image in a noscript, whose content discovery parses again.
_EVERY_LINK_ELEMENT = """<html><head><link rel="stylesheet" href="/site.css">
<link rel="canonical" href="/canonical"><link rel="next" href="/next">
<link rel="alternate" hreflang="de" href="/de"><link rel="amphtml" href="/amp">
<link rel="alternate" media="handheld" href="/mobile"><link rel="icon" href="/favicon.ico">
<meta http-equiv="refresh" content="30; url=/news"><script src="/app.js"></script></head>
<body><a href="/about">About</a>
<img src="/map.png" usemap="#m"><map name="m"><area href="/north" alt="North"></map>
<iframe src="/widget.html"></iframe>
<img src="/logo.png" srcset="/logo@2x.png 2x" alt="Logo">
<picture><source srcset="/hero.webp" type="image/webp"><img src="/hero.jpg" alt=""></picture>
<video src="/intro.mp4" poster="/intro.jpg"><track src="/intro.vtt" kind="captions"></video>
<video controls><source src="/demo.mp4" type="video/mp4"></video>
<audio src="/theme.mp3"><source src="/song.mp3"><track src="/song.vtt"></audio>
<embed src="/tour.swf"><object data="/brochure.pdf"></object>
<noscript><img src="/pixel.gif" alt=""></noscript></body></html>"""
_FRAMESET = '<html><frameset cols="20%,80%"><frame src="/menu.html"><frame src="/main.html">'

_EXPECTED_SOURCES: dict[str, set[tuple[str, str]]] = {
    "hyperlink": {("a", "href"), ("area", "href")},
    "canonical": {("link", "href")},
    "pagination": {("link", "href")},
    "hreflang": {("link", "href")},
    "iframe": {("iframe", "src"), ("frame", "src")},
    "meta_refresh": {("meta", "content")},
    "http_refresh": set(),
    "image": {("img", "src"), ("img", "srcset"), ("source", "srcset"), ("video", "poster")},
    "css": {("link", "href")},
    "javascript": {("script", "src")},
    "video": {("video", "src"), ("source", "src"), ("track", "src")},
    "audio": {("audio", "src"), ("source", "src"), ("track", "src")},
    "media": {("embed", "src"), ("object", "data")},
    "amphtml": {("link", "href")},
    "mobile_alternate": {("link", "href")},
    "misc": {("link", "href")},
    "xml_sitemap": set(),
    "sitemap_hreflang": set(),
    "javascript_redirect": set(),
}


def test_discovered_link_sources_match_the_type_table() -> None:
    rows = page_link_rows(_EVERY_LINK_ELEMENT) + page_link_rows(_FRAMESET)
    found: dict[str, set[tuple[str | None, str | None]]] = {
        name: set() for name in _EXPECTED_SOURCES
    }
    for row in rows:
        found.setdefault(row.type, set()).add((row.element, row.attribute))
    declared = {name: set(info.sources) for name, info in LINK_TYPES.items()}

    assert (found, declared) == (_EXPECTED_SOURCES, _EXPECTED_SOURCES), (
        "Link sources must agree per LinkType: update the literal fixture or LINK_TYPES.sources"
    )


def test_every_element_and_attribute_discovery_reads_is_enumerated() -> None:
    rows = page_link_rows(_EVERY_LINK_ELEMENT) + page_link_rows(_FRAMESET)

    assert (
        {row.element for row in rows},
        {row.attribute for row in rows},
        {element for info in LINK_TYPES.values() for element, _ in info.sources},
        {attribute for info in LINK_TYPES.values() for _, attribute in info.sources},
    ) == (
        set(literal_values(LinkElement)),
        set(literal_values(LinkAttribute)),
        set(literal_values(LinkElement)),
        set(literal_values(LinkAttribute)),
    ), "Link source Literals must be covered: add the pair to LINK_TYPES and the literal fixture"


def test_link_type_table_covers_the_link_type_literal() -> None:
    assert set(LINK_TYPES) == set(literal_values(LinkType)), (
        "every LinkType must be declared: add its request policy and sources to LINK_TYPES"
    )


def test_header_sources_are_recorded_without_dom_pairs() -> None:
    rows = response_link_rows(
        "application/pdf",
        headers=(
            (
                "Link",
                '</c>; rel="canonical", </next>; rel="next", </de>; rel="alternate"; hreflang="de"',
            ),
            ("Refresh", "0; url=/refreshed"),
        ),
    )

    assert (
        [(row.type, row.element, row.attribute) for row in rows],
        {name for name, info in LINK_TYPES.items() if info.header},
    ) == (
        [
            ("canonical", None, None),
            ("pagination", None, None),
            ("hreflang", None, None),
            ("http_refresh", None, None),
        ],
        {"canonical", "pagination", "hreflang", "http_refresh"},
    ), "header sources must agree: keep DOM pairs unset and match LINK_TYPES.header to discovery"
