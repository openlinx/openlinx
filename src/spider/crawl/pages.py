"""Page preparation: one pure function of a response, behind an executor (020-add-crawl-core D9)."""

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


@dataclass(frozen=True, slots=True)
class PageSettings:
    """The settings snapshot: built once per Crawl, and given to each 026 worker once."""

    scope: ScopeRules


class PreparedPage(msgspec.Struct, frozen=True, kw_only=True):
    links: tuple[DiscoveredLink, ...]


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
    return PreparedPage(links=tuple(links))


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
