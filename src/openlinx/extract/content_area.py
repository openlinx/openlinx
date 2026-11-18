"""Carry Content Area selectors as immutable Page extractor configuration."""

import msgspec


class ContentArea(msgspec.Struct, frozen=True, kw_only=True):
    """The Page extractor's config: the [content_area] selectors, compiled by each parser."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ("nav", "header", "footer")
