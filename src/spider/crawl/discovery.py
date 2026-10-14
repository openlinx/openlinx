"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5)."""

from collections.abc import Iterable

from spider.crawl.links import DiscoveredLink
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import LinkType, NewUrl

# Every Link of these types is recorded: one in the Scope is followed, any other checked
# or skipped.
_FOLLOWED: frozenset[LinkType] = frozenset({"hyperlink", "meta_refresh"})


def discovered_urls(
    links: Iterable[DiscoveredLink], scope: ScopeRules, depth: int
) -> tuple[NewUrl, ...]:
    """One row per URL, from its first Link in document order (design D5)."""
    # A Page names most URLs several times, and each row costs its unit an insert.
    first: dict[NormalizedUrl, DiscoveredLink] = {}
    for link in links:
        if link.type in _FOLLOWED:
            first.setdefault(link.target, link)
    return tuple(_new_url(link, scope, depth) for link in first.values())


def _new_url(link: DiscoveredLink, scope: ScopeRules, depth: int) -> NewUrl:
    decision = scope.decide(link.target)
    return NewUrl(
        url=link.target,
        crawl_depth=depth,
        discovered_via=link.type,
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
    )
