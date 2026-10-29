"""`<noscript>` read as a browser that runs scripts reads it (020-add-crawl-core D5; seam 4)."""

from datetime import UTC, datetime

import msgspec
from hypothesis import given
from hypothesis import strategies as st
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import (
    PageInput,
    PageSettings,
    PreparedPage,
    extractor,
    prepare_page,
)
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl

SITE = NormalizedUrl("http://site.test/")


class _Head(msgspec.Struct, frozen=True):
    children: tuple[str, ...]
    titles: tuple[str, ...]


def _head(tree: LexborHTMLParser, page: PageInput, config: None) -> _Head:
    head = tree.head
    return _Head(
        children=() if head is None else tuple(node.tag or "" for node in head.iter()),
        titles=tuple(node.text() for node in tree.css("title")),
    )


def _prepared(html: str) -> tuple[PreparedPage, _Head]:
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", "text/html"),),
        body=html.encode(),
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=1,
    )
    settings = PageSettings(
        scope=scope_rules(SITE), extractors=(extractor("head", _head, None),), strip_params=None
    )
    page = prepare_page(SITE, response, settings)
    head = dict(page.outputs)["head"]
    assert isinstance(head, _Head)
    return page, head


def test_a_head_noscript_pixel_keeps_the_head_elements_in_head() -> None:
    _, head = _prepared(
        '<head><title>T</title><noscript><img src="/px"></noscript>'
        '<link rel="canonical" href="/c"><link rel="alternate" hreflang="de" href="/de">'
        '<meta name="description" content="D"></head><body><p>B</p>'
    )

    assert head.children == ("title", "noscript", "link", "link", "meta")


def test_a_title_and_a_robots_meta_in_a_head_noscript_are_ignored() -> None:
    page, head = _prepared(
        '<head><noscript><title>N</title><meta name="robots" content="noindex"></noscript>'
        "<title>T</title></head>"
    )

    assert (head.titles, page.directives.meta_robots) == (("T",), None)


_PIECES = st.sampled_from(
    [
        "<noscript>",
        "</noscript>",
        "<NOSCRIPT a='>'>",
        "<noscript/>",
        "<noscript",
        '<a href="/a">',
        "<img src=/i>",
        '<link rel="canonical" href="/c">',
        '<meta name="robots" content="noindex">',
        "<template>",
        "</template>",
        "<!--",
        "-->",
        "<script>",
        "</script>",
        "<title>",
        "<head>",
        "<body>",
        ">",
        '"',
        "<",
    ]
)


@given(st.lists(_PIECES | st.text(max_size=4)).map("".join))
def test_preparing_any_page_with_noscript_tags_gives_a_page(html: str) -> None:
    assert isinstance(_prepared(html)[0], PreparedPage)


def test_a_literal_noscript_start_tag_leaves_a_later_noscript_hidden() -> None:
    page, head = _prepared(
        "<head><script>s.replace('<noscript>', '')</script><noscript><img src=\"/px\">"
        '<meta name="robots" content="noindex"></noscript><link rel="canonical" href="/c">'
        "</head>"
    )

    assert (page.directives.meta_robots, head.children) == (
        None,
        ("script", "noscript", "link"),
    )


def test_a_noscript_in_a_template_of_the_page_gives_no_link() -> None:
    page, _ = _prepared('<template><noscript><a href="/t"></a></noscript></template>')

    assert page.html_links == ()


def test_a_literal_noscript_tag_in_text_or_an_attribute_is_left_as_it_is() -> None:
    page, head = _prepared('<head><title>a<noscript>b</title></head><a href="/p<noscript>">x</a>')

    assert (head.titles, [link.raw for link in page.html_links]) == (
        ("a<noscript>b",),
        ["/p<noscript>"],
    )


def test_a_noscript_s_links_are_placed_where_the_noscript_is() -> None:
    # The tracking pixels of an analytics snippet, one in the head and one in the body.
    page, _ = _prepared(
        '<head><noscript><img height="1" width="1" style="display:none" '
        'src="https://px.example/tr?id=1&amp;noscript=1"></noscript></head>'
        '<body><noscript><iframe src="https://tags.example/ns.html?id=2" height="0" width="0">'
        "</iframe></noscript><p>B</p></body>"
    )

    assert [(link.target, link.declared_in) for link in page.html_links] == [
        ("https://px.example/tr?id=1&noscript=1", "head"),
        ("https://tags.example/ns.html?id=2", "body"),
    ]
