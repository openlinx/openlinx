"""Reference resolution and Links through one policy-aware factory (020 D5, D19; 023 D12)."""

import msgspec

from openlinx.crawl.following import skip_reason
from openlinx.crawl.reference_urls import (
    C0_OR_SPACE as C0_OR_SPACE,
)
from openlinx.crawl.reference_urls import (
    resolve_base as resolve_base,
)
from openlinx.crawl.reference_urls import (
    resolve_reference as resolve_reference,
)
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import (
    DeclaredIn,
    DiscoverySkipReason,
    LinkAttribute,
    LinkElement,
    LinkType,
)


class DiscoveredLink(msgspec.Struct, frozen=True, kw_only=True):
    type: LinkType
    target: NormalizedUrl
    raw: str
    element: LinkElement | None
    attribute: LinkAttribute | None
    rel: tuple[str, ...]
    nofollow: bool
    # Why the Crawl does not request the target through this Link (openlinx.crawl.following).
    skip_reason: DiscoverySkipReason | None
    declared_in: DeclaredIn
    ordinal: int
    is_internal: bool

    @property
    def requests_target(self) -> bool:
        return self.skip_reason is None


def discovered_link(
    link_type: LinkType,
    target: NormalizedUrl,
    raw: str,
    *,
    element: LinkElement | None,
    attribute: LinkAttribute | None,
    rel: tuple[str, ...],
    declared_in: DeclaredIn,
    ordinal: int,
    is_internal: bool,
    page_nofollow: bool,
    follow_nofollow: bool,
) -> DiscoveredLink:
    """A Link of the document or of a header: its nofollow is its rel's, and the follow rule
    gives its skip reason (design D5)."""
    nofollow = "nofollow" in rel
    return DiscoveredLink(
        type=link_type,
        target=target,
        raw=raw,
        element=element,
        attribute=attribute,
        rel=rel,
        nofollow=nofollow,
        skip_reason=skip_reason(
            link_type, nofollow, page_nofollow=page_nofollow, follow_nofollow=follow_nofollow
        ),
        declared_in=declared_in,
        ordinal=ordinal,
        is_internal=is_internal,
    )
