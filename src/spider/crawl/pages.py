"""Page preparation: one pure function of a response, behind an executor (020-add-crawl-core D9)."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.decoding import decode_html
from spider.crawl.fetcher import FetchResult
from spider.crawl.links import DiscoveredLink, base_url, links_in_tree
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import ParseError

_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})


def is_html_type(content_type: str | None) -> bool:
    """The one rule of an HTML response, which 030's Page predicate imports (design D5)."""
    media_type = (content_type or "").partition(";")[0]
    return media_type.strip().lower() in _HTML_TYPES


class PageInput(msgspec.Struct, frozen=True, kw_only=True):
    """What an extractor gets besides the tree; built in the process that parses the Page."""

    url: NormalizedUrl
    status_code: int
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    # Of the decoded document, in characters.
    length: int
    links: tuple[DiscoveredLink, ...]
    # A reference to the snapshot the process holds, never a copy.
    settings: "PageSettings"


@dataclass(frozen=True, slots=True)
class Extractor:
    """Pure and module-level, so that a 026 worker imports it by name."""

    name: str
    extract: Callable[[LexborHTMLParser, PageInput], msgspec.Struct]


@dataclass(frozen=True, slots=True)
class PageSettings:
    """The settings snapshot: built once per Crawl, and given to each 026 worker once."""

    scope: ScopeRules
    extractors: tuple[Extractor, ...] = ()


class PreparedPage(msgspec.Struct, frozen=True, kw_only=True):
    links: tuple[DiscoveredLink, ...]
    # By extractor name, without the outputs of extractors that failed.
    outputs: tuple[tuple[str, msgspec.Struct], ...] = ()
    parse_error: ParseError | None = None
    parse_error_message: str | None = None


def prepare_page(url: NormalizedUrl, response: FetchResult, settings: PageSettings) -> PreparedPage:
    """Decodes and parses once; the link extractor and later extractors share the tree."""
    decoded = decode_html(response.body, response.header("Content-Type"))
    tree = LexborHTMLParser(decoded.text)
    links = links_in_tree(
        tree,
        base=base_url(tree, url, decoded.encoding),
        encoding=decoded.encoding,
        is_internal=partial(_is_internal, settings.scope),
    )
    page = PageInput(
        url=url,
        status_code=response.status_code,
        headers=response.headers,
        length=len(decoded.text),
        links=tuple(links),
        settings=settings,
    )
    outputs: list[tuple[str, msgspec.Struct]] = []
    failures: list[str] = []
    for extractor in settings.extractors:
        try:
            output = extractor.extract(tree, page)
            # Only a msgspec struct crosses 026's process boundary as it is.
            if not isinstance(output, msgspec.Struct):
                raise TypeError(f"{extractor.name} returned {type(output).__name__}")
            outputs.append((extractor.name, output))
        # An extractor is later changes' code: its failure costs only its output (design D16).
        except Exception as error:
            failures.append(f"{extractor.name}: {type(error).__name__}")
    return PreparedPage(
        links=page.links,
        outputs=tuple(outputs),
        parse_error="extractor_error" if failures else None,
        parse_error_message="; ".join(failures) or None,
    )


def _is_internal(scope: ScopeRules, url: NormalizedUrl) -> bool:
    return scope.decide(url).is_internal


class PageExecutor(Protocol):
    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage: ...


class InProcessExecutor:
    """Prepares Pages on the event loop's thread; 026 puts a process pool behind the seam."""

    def __init__(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        return prepare_page(url, response, self._settings)
