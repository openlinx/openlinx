"""Request policy from LINK_TYPES and HTTP redirect targets (023 D12; 022 D2)."""

import re

from openlinx.crawl.reference_urls import resolve_reference
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import LINK_TYPES, DiscoverySkipReason, LinkType

# The statuses whose Location is followed; a 300, 304 or 305 keeps its Location and no target.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def is_redirection(status_code: int) -> bool:
    """A 3xx response: it keeps its Location, and only REDIRECT_STATUSES give a target."""
    return 300 <= status_code < 400


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


def redirect_target(
    url: NormalizedUrl,
    status_code: int,
    location: str | None,
    strip_params: re.Pattern[str] | None,
) -> NormalizedUrl | None:
    """The URL a response redirects to, resolved against `url` as a Link's reference is, or
    None when the status is no redirect or the Location gives no http URL."""
    if status_code not in REDIRECT_STATUSES or location is None:
        return None
    return resolve_reference(url, location, codec=None, strip_params=strip_params)
