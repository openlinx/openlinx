"""What 020's page preparation gives for a synthetic Page, and the extractor that ends its worker.

The benchmark's direct mode prepares Pages with `prepared_page` instead of parsing them
(026-add-parse-pool D6).
"""

import os
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.links import DiscoveredLink
from spider.crawl.pages import Extractor, PageInput, PreparedPage
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import LinkType
from tests.fixture_site.synthetic.site import (
    LOSES_LINKS,
    OUTCOMES,
    SyntheticSite,
    page_number,
)

END_WORKER_EXIT = 70
# 020 builds these in its tasks 7.7, 7.8, 7.9 and 8.12; until then a canonical or amphtml
# <link> is a misc Link, and a refresh gives none.
_PREPARED_AS: Mapping[str, LinkType | None] = {
    "canonical": "misc",
    "amphtml": "misc",
    "meta_refresh": None,
    "http_refresh": None,
}
_END_WORKER_SELECTOR = 'meta[name="spider-benchmark"][content="end-worker"]'


def prepared_page(site: SyntheticSite, url: NormalizedUrl, scope: ScopeRules) -> PreparedPage:
    parts = urlsplit(url)
    n = page_number(parts.path, site.pages)
    if n is None:
        raise ValueError(f"{url} is not a Page of the synthetic site")
    fault = site.fault(n)
    if fault in LOSES_LINKS:
        return PreparedPage(links=(), parse_error=OUTCOMES[fault]["parse_error"])
    # A target of the model is an absolute URL or a path from the root, which joins the origin.
    origin = f"{parts.scheme}://{parts.netloc}"
    links: list[DiscoveredLink] = []
    for link in site.page_model(n):
        # The model spells each type as 020's LinkType does.
        link_type = _PREPARED_AS.get(link.type, cast(LinkType, link.type))
        if link_type is None:
            continue
        target = normalize_url(link.target if "://" in link.target else origin + link.target)
        assert isinstance(target, str)
        links.append(
            DiscoveredLink(
                type=link_type,
                target=target,
                raw=link.target,
                element=link.element,
                attribute=link.attribute,
                rel=(),
                nofollow=False,
                declared_in="html",
                ordinal=len(links) + 1,
                is_internal=scope.decide(target).is_internal,
            )
        )
    return PreparedPage(links=tuple(links))


class Continued(msgspec.Struct, frozen=True):
    """The end-worker extractor's output on a Page without the marker."""


def _end_worker(tree: LexborHTMLParser, page: PageInput) -> Continued:
    if tree.css_first(_END_WORKER_SELECTOR) is not None:
        # As a native parser's crash would: no exception, no cleanup.
        os._exit(END_WORKER_EXIT)
    return Continued()


END_WORKER_EXTRACTOR = Extractor("benchmark_end_worker", _end_worker)
