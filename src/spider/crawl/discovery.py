"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5)."""

from collections.abc import Iterable

from spider.crawl.links import DiscoveredLink
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import DiscoverySkipReason, LinkType, NewUrl

# The spec's Link type table: through these a URL in the Scope is followed, any other checked.
_FOLLOWED: frozenset[LinkType] = frozenset(
    {"hyperlink", "canonical", "pagination", "hreflang", "iframe", "meta_refresh", "http_refresh"}
)
_NOT_FOLLOWED: frozenset[LinkType] = frozenset({"amphtml", "mobile_alternate", "misc"})


def discovered_urls(
    links: Iterable[DiscoveredLink],
    scope: ScopeRules,
    depth: int,
    *,
    nofollow: bool = False,
    follow_nofollow: bool = False,
) -> tuple[NewUrl, ...]:
    """One row per URL, followed when any of its Links is, in document order (design D5).

    `nofollow` is a page-level nofollow, which applies to every hyperlink of the Page;
    `follow_nofollow` treats nofollow hyperlinks like any other (--follow-nofollow).
    """
    # A Page names most URLs several times, and each row costs its unit an insert.
    chosen: dict[NormalizedUrl, tuple[DiscoveredLink, DiscoverySkipReason | None]] = {}
    for link in links:
        # Resources are requested with group 9; until then they are not recorded.
        if link.type not in _FOLLOWED and link.type not in _NOT_FOLLOWED:
            continue
        reason = _skip_reason(link, nofollow, follow_nofollow)
        known = chosen.get(link.target)
        # A followed Link gives the URL's provenance; it keeps its first place in the order.
        if known is None or (known[1] is not None and reason is None):
            chosen[link.target] = (link, reason)
    return tuple(_new_url(link, reason, scope, depth) for link, reason in chosen.values())


def _skip_reason(
    link: DiscoveredLink, nofollow: bool, follow_nofollow: bool
) -> DiscoverySkipReason | None:
    if link.type not in _FOLLOWED:
        return "link_type_not_followed"
    if link.type == "hyperlink" and (link.nofollow or nofollow) and not follow_nofollow:
        return "nofollow"
    return None


def _new_url(
    link: DiscoveredLink, reason: DiscoverySkipReason | None, scope: ScopeRules, depth: int
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
