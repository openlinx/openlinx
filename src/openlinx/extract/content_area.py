"""The Content Area's selectors: the Page extractor's config (030-add-page-data D13)."""

import msgspec


class ContentArea(msgspec.Struct, frozen=True, kw_only=True):
    """The Page extractor's config: the [content_area] selectors, compiled by each parser."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ("nav", "header", "footer")
