"""Whether the Crawl requests a Link's target: the Link type table and nofollow
(020-add-crawl-core D5). The Scope plays no part, so 030's shortest paths over the stored Links
agree with the depths the engine records."""

from spider.store.records import LinkType

# The spec's Link type table: through these a URL in the Scope is followed, through RESOURCES
# it is requested as a Resource, and through any other type it is recorded skipped.
_FOLLOWED: frozenset[LinkType] = frozenset(
    {"hyperlink", "canonical", "pagination", "hreflang", "iframe", "meta_refresh", "http_refresh"}
)
RESOURCES: frozenset[LinkType] = frozenset(
    {"image", "css", "javascript", "video", "audio", "media"}
)
REQUESTED_TYPES = _FOLLOWED | RESOURCES


def requests_target(
    link_type: LinkType, nofollow: bool, *, page_nofollow: bool, follow_nofollow: bool
) -> bool:
    """`nofollow` is the Link's own rel, `page_nofollow` the Page's robots directives', and
    either applies to hyperlinks only; `follow_nofollow` lifts both (--follow-nofollow)."""
    if link_type not in REQUESTED_TYPES:
        return False
    return link_type != "hyperlink" or follow_nofollow or not (nofollow or page_nofollow)
