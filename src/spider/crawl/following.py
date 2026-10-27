"""Whether the Crawl requests a Link's target: the Link type table and nofollow
(020-add-crawl-core D5). The Scope plays no part, so 030's shortest paths over the stored Links
agree with the depths the engine records."""

from spider.store.records import RESOURCE_LINK_TYPES, DiscoverySkipReason, LinkType

# The spec's Link type table: through these a URL in the Scope is followed, through RESOURCES
# it is requested as a Resource, and through any other type it is recorded skipped.
_FOLLOWED: frozenset[LinkType] = frozenset(
    {"hyperlink", "canonical", "pagination", "hreflang", "iframe", "meta_refresh", "http_refresh"}
)
RESOURCES = RESOURCE_LINK_TYPES
_REQUESTED = _FOLLOWED | RESOURCES


def skip_reason(
    link_type: LinkType, nofollow: bool, *, page_nofollow: bool, follow_nofollow: bool
) -> DiscoverySkipReason | None:
    """Why the Crawl does not request the target through the Link, or None when it does.

    `nofollow` is the Link's own rel, `page_nofollow` the Page's robots directives', and
    either applies to hyperlinks only; `follow_nofollow` lifts both (--follow-nofollow)."""
    if link_type not in _REQUESTED:
        return "link_type_not_followed"
    if link_type == "hyperlink" and (nofollow or page_nofollow) and not follow_nofollow:
        return "nofollow"
    return None
