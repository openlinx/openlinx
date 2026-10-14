"""What 020's page preparation gives for a synthetic Page, and the extractor that ends its worker.

The benchmark's direct mode prepares Pages with `prepared_page` instead of parsing them
(design D6 of 026-add-parse-pool).
"""

import os
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.directives import robots_directives
from spider.crawl.links import DiscoveredLink
from spider.crawl.pages import Extractor, PageInput, PageSettings, PreparedPage
from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import LinkType
from tests.fixture_site.synthetic.site import (
    LOSES_LINKS,
    OUTCOMES,
    SyntheticSite,
    page_number,
)

END_WORKER_EXIT = 70
# The model's Links that a response header declares; the others are the HTML's.
HEADER_TYPES = frozenset({"http_refresh"})
# 020 builds an HTML <link rel="canonical"> as a canonical Link in its task 8.12; until then it
# is a misc Link, which the equivalence test checks, so it fails here once 8.12 lands.
_PREPARED_AS: Mapping[str, LinkType] = {"canonical": "misc"}
_END_WORKER_SELECTOR = 'meta[name="spider-benchmark"][content="end-worker"]'


def prepared_page(site: SyntheticSite, url: NormalizedUrl, settings: PageSettings) -> PreparedPage:
    parts = urlsplit(url)
    n = page_number(parts.path, site.pages)
    if n is None:
        raise ValueError(f"{url} is not a Page of the synthetic site")
    fault = site.fault(n)
    # No Page of the site has a meta robots or an X-Robots-Tag.
    directives = robots_directives((), (), settings.robots_token)
    if fault in LOSES_LINKS:
        return PreparedPage(
            links=(), directives=directives, parse_error=OUTCOMES[fault]["parse_error"]
        )
    # A target of the model is an absolute URL or a path from the root, which joins the origin.
    origin = f"{parts.scheme}://{parts.netloc}"
    links: list[DiscoveredLink] = []
    for link in site.page_model(n):
        target = normalize_url(link.target if "://" in link.target else origin + link.target)
        assert isinstance(target, str)
        links.append(
            DiscoveredLink(
                # The model spells each type as 020's LinkType does.
                type=_PREPARED_AS.get(link.type, cast(LinkType, link.type)),
                target=target,
                raw=link.target,
                element=link.element,
                attribute=link.attribute,
                rel=(),
                nofollow=False,
                declared_in="http_header" if link.type in HEADER_TYPES else "html",
                ordinal=len(links) + 1,
                is_internal=settings.scope.decide(target).is_internal,
            )
        )
    return PreparedPage(links=tuple(links), directives=directives)


class Continued(msgspec.Struct, frozen=True):
    """The end-worker extractor's output on a Page without the marker."""


def _end_worker(tree: LexborHTMLParser, page: PageInput) -> Continued:
    if tree.css_first(_END_WORKER_SELECTOR) is not None:
        # As a native parser's crash would: no exception, no cleanup.
        os._exit(END_WORKER_EXIT)
    return Continued()


END_WORKER_EXTRACTOR = Extractor("benchmark_end_worker", _end_worker)
