"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5)."""

from collections.abc import Iterable

from spider.crawl.links import DiscoveredLink
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import LinkType, NewUrl, SkipReason

# The spec's Link type table: through these a URL in the Scope is followed, any other checked.
_FOLLOWED: frozenset[LinkType] = frozenset(
    {"hyperlink", "canonical", "pagination", "hreflang", "iframe", "meta_refresh", "http_refresh"}
)
_NOT_FOLLOWED: frozenset[LinkType] = frozenset({"amphtml", "mobile_alternate", "misc"})


def discovered_urls(
    links: Iterable[DiscoveredLink], scope: ScopeRules, depth: int
) -> tuple[NewUrl, ...]:
    """One row per URL, followed when any of its Links is, in document order (design D5)."""
    # A Page names most URLs several times, and each row costs its unit an insert.
    chosen: dict[NormalizedUrl, tuple[DiscoveredLink, SkipReason | None]] = {}
    for link in links:
        # Resources are requested with group 9; until then they are not recorded.
        if link.type not in _FOLLOWED and link.type not in _NOT_FOLLOWED:
            continue
        reason: SkipReason | None = None if link.type in _FOLLOWED else "link_type_not_followed"
        known = chosen.get(link.target)
        # A followed Link gives the URL's provenance; it keeps its first place in the order.
        if known is None or (known[1] is not None and reason is None):
            chosen[link.target] = (link, reason)
    return tuple(_new_url(link, reason, scope, depth) for link, reason in chosen.values())


def _new_url(
    link: DiscoveredLink, reason: SkipReason | None, scope: ScopeRules, depth: int
) -> NewUrl:
    decision = scope.decide(link.target)
    return NewUrl(
        url=link.target,
        crawl_depth=depth,
        discovered_via=link.type,
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
        skip_reason=reason,
    )
