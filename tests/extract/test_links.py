"""Link attributes (030-add-page-data, page-data; seam 4)."""

from openlinx.store.page_records import LinkAttribute, LinkElement
from openlinx.store.schema import literal_values
from tests.support.page_data import page_link_rows, response_link_rows


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
<meta http-equiv="refresh" content="30; url=/news"><script src="/app.js"></script></head>
<body><a href="/about">About</a>
<img src="/map.png" usemap="#m"><map name="m"><area href="/north" alt="North"></map>
<iframe src="/widget.html"></iframe>
<img src="/logo.png" srcset="/logo@2x.png 2x" alt="Logo">
<picture><source srcset="/hero.webp" type="image/webp"><img src="/hero.jpg" alt=""></picture>
<video src="/intro.mp4" poster="/intro.jpg"><track src="/intro.vtt" kind="captions"></video>
<video controls><source src="/demo.mp4" type="video/mp4"></video>
<audio src="/theme.mp3"></audio><embed src="/tour.swf"><object data="/brochure.pdf"></object>
<noscript><img src="/pixel.gif" alt=""></noscript></body></html>"""
_FRAMESET = '<html><frameset cols="20%,80%"><frame src="/menu.html"><frame src="/main.html">'


def test_every_element_and_attribute_discovery_reads_is_enumerated() -> None:
    rows = page_link_rows(_EVERY_LINK_ELEMENT) + page_link_rows(_FRAMESET)

    assert (
        {row.element for row in rows},
        {row.attribute for row in rows},
    ) == (set(literal_values(LinkElement)), set(literal_values(LinkAttribute)))
