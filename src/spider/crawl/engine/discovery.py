"""The URLs that a Page links to, as the engine records them (020-add-crawl-core D1, D5)."""

from collections.abc import Iterable

from spider.crawl.following import REQUESTED_TYPES, RESOURCES
from spider.crawl.references import DiscoveredLink
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import DiscoverySkipReason, NewUrl


def discovered_urls(
    links: Iterable[DiscoveredLink],
    scope: ScopeRules,
) -> tuple[NewUrl, ...]:
    """One row per URL, followed when any of its Links requests it, in document order
    (design D5)."""
    # A Page names most URLs several times, and each row costs its unit an insert.
    chosen: dict[NormalizedUrl, tuple[DiscoveredLink, DiscoverySkipReason | None]] = {}
    for link in links:
        reason = _skip_reason(link)
        known = chosen.get(link.target)
        # The Link that gives the URL's provenance; the URL keeps its first place in the order.
        if known is None or _outranks(link, reason, *known):
            chosen[link.target] = (link, reason)
    return tuple(_new_url(link, reason, scope) for link, reason in chosen.values())


def _outranks(
    link: DiscoveredLink,
    reason: DiscoverySkipReason | None,
    known: DiscoveredLink,
    known_reason: DiscoverySkipReason | None,
) -> bool:
    # A requested Link outranks an unrequested one, and a Resource Link a followed one: being a
    # Resource is the Link's own property, which the depth limit and the barrier read (D5).
    if reason is not None:
        return False
    return known_reason is not None or (link.type in RESOURCES and known.type not in RESOURCES)


def _skip_reason(link: DiscoveredLink) -> DiscoverySkipReason | None:
    if link.requests_target:
        return None
    return "nofollow" if link.type in REQUESTED_TYPES else "link_type_not_followed"


def _new_url(link: DiscoveredLink, reason: DiscoverySkipReason | None, scope: ScopeRules) -> NewUrl:
    decision = scope.decide(link.target)
    return NewUrl(
        url=link.target,
        discovered_via=link.type,
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
        skip_reason=reason,
    )
