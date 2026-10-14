"""`<noscript>` read as a browser that runs scripts reads it (020-add-crawl-core D5, task 15.1;
seam 4)."""

from datetime import UTC, datetime

import msgspec
import pytest
from hypothesis import given
from hypothesis import strategies as st
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.fetcher import FetchResult
from spider.crawl.noscript import MARKER, without_noscript
from spider.crawl.pages import Extractor, PageInput, PageSettings, PreparedPage, prepare_page
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl

SITE = NormalizedUrl("http://site.test/")
TEMPLATE = f'<template {MARKER}="0"'


class _Head(msgspec.Struct, frozen=True):
    children: tuple[str, ...]
    titles: tuple[str, ...]


def _head(tree: LexborHTMLParser, page: PageInput) -> _Head:
    head = tree.head
    return _Head(
        children=() if head is None else tuple(node.tag or "" for node in head.iter()),
        titles=tuple(node.text() for node in tree.css("title")),
    )


def _prepared(html: str) -> tuple[PreparedPage, _Head]:
    response = FetchResult(
        status_code=200,
        headers=(("Content-Type", "text/html"),),
        body=html.encode(),
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=1,
    )
    settings = PageSettings(scope=scope_rules(SITE), extractors=(Extractor("head", _head),))
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

    assert head.children == ("title", "template", "link", "link", "meta")


def test_a_title_and_a_robots_meta_in_a_head_noscript_are_ignored() -> None:
    page, head = _prepared(
        '<head><noscript><title>N</title><meta name="robots" content="noindex"></noscript>'
        "<title>T</title></head>"
    )

    assert (head.titles, page.directives.meta_robots) == (("T",), None)


@pytest.mark.parametrize(
    ("html", "renamed", "noscripts"),
    [
        (
            "<p>noscript</p><noscriptx>&lt;noscript&gt;",
            "<p>noscript</p><noscriptx>&lt;noscript&gt;",
            (),
        ),
        (
            '<NoScript class="a"><a href=/x></NOSCRIPT >',
            f'{TEMPLATE} class="a"><a href=/x></template >',
            ("<a href=/x>",),
        ),
        ("<noscript/>", f"{TEMPLATE}/>", ("",)),
        ("<noscript", TEMPLATE, ("",)),
        # A browser that runs scripts ends the outer <noscript> at the first end tag.
        (
            "<noscript>A<noscript>B</noscript>C</noscript>",
            f'{TEMPLATE}>A<template {MARKER}="1">B</template>C</template>',
            ("A<noscript>B", "B"),
        ),
        # Known edges: a literal <noscript is renamed wherever it stands (design Risks).
        ("<!-- <noscript> -->", f"<!-- {TEMPLATE}> -->", (" -->",)),
        ('<script>"<noscript>"</script>', f'<script>"{TEMPLATE}>"</script>', ('"</script>',)),
        ("<style><noscript></style>", f"<style>{TEMPLATE}></style>", ("</style>",)),
        ('<a title="<noscript>">', f'<a title="{TEMPLATE}>">', ('">',)),
        ("<title><noscript></title>", f"<title>{TEMPLATE}></title>", ("</title>",)),
        ("<textarea><noscript></textarea>", f"<textarea>{TEMPLATE}></textarea>", ("</textarea>",)),
    ],
)
def test_only_noscript_tags_are_renamed_wherever_they_stand(
    html: str, renamed: str, noscripts: tuple[str, ...]
) -> None:
    assert without_noscript(html) == (renamed, noscripts)


@given(st.text().filter(lambda text: "noscript" not in text.lower()))
def test_html_without_a_noscript_tag_is_left_as_it_is(text: str) -> None:
    assert without_noscript(text) == (text, ())


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
        f'<template {MARKER}="9">',
        f'<template {MARKER}="x">',
        f'<template {MARKER}="{"9" * 5000}">',
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


@pytest.mark.parametrize("index", ["1", "x", "9" * 5000])
def test_a_template_of_the_page_with_the_marker_gives_no_link(index: str) -> None:
    page, _ = _prepared(f'<noscript></noscript><template {MARKER}="{index}"><a href="/t"></a>')

    assert page.document_links == ()
