"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5)."""

from collections.abc import Iterable

from spider.crawl.links import DiscoveredLink
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import NewUrl


def discovered_urls(
    links: Iterable[DiscoveredLink], scope: ScopeRules, depth: int
) -> tuple[NewUrl, ...]:
    """One row per URL, from its first Link in document order (design D5)."""
    # A Page names most URLs several times, and each row costs its unit an insert.
    first: dict[NormalizedUrl, DiscoveredLink] = {}
    for link in links:
        # Every hyperlink is recorded: one in the Scope is followed, any other checked or skipped.
        if link.type == "hyperlink":
            first.setdefault(link.target, link)
    return tuple(_new_url(url, scope, depth) for url in first)


def _new_url(url: NormalizedUrl, scope: ScopeRules, depth: int) -> NewUrl:
    decision = scope.decide(url)
    return NewUrl(
        url=url,
        crawl_depth=depth,
        discovered_via="hyperlink",
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
    )
