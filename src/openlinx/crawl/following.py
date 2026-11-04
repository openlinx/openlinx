"""Request policy from the Link type table and nofollow, independent of Scope (023 D12)."""

from openlinx.store.records import LINK_TYPES, DiscoverySkipReason, LinkType


def skip_reason(
    link_type: LinkType, nofollow: bool, *, page_nofollow: bool, follow_nofollow: bool
) -> DiscoverySkipReason | None:
    """Why the Crawl does not request the target through the Link, or None when it does.

    `nofollow` is the Link's own rel, `page_nofollow` the Page's robots directives', and
    either applies to hyperlinks only; `follow_nofollow` lifts both (--follow-nofollow)."""
    if LINK_TYPES[link_type].requested is None:
        return "link_type_not_followed"
    if link_type == "hyperlink" and (nofollow or page_nofollow) and not follow_nofollow:
        return "nofollow"
    return None
