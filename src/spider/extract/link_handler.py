"""The links handler: a row for each Link of a URL's result (030-add-page-data D4)."""

from collections.abc import Iterable

from spider.crawl.engine.hooks import UrlResult
from spider.crawl.references import DiscoveredLink
from spider.extract.page_links import PAGE_LINKS, LinkAttributes
from spider.store.page_records import LinkRow


def link_rows(result: UrlResult) -> Iterable[LinkRow]:
    found = PAGE_LINKS.output(result.outputs)
    # Header Links, and every Link of a Page whose Link extractor failed, have no attributes.
    attributes = {} if found is None else {each.ordinal: each for each in found.links}
    return tuple(_row(result.url_id, link, attributes.get(link.ordinal)) for link in result.links)


def _row(source_url_id: int, link: DiscoveredLink, attributes: LinkAttributes | None) -> LinkRow:
    return LinkRow(
        source_url_id=source_url_id,
        ordinal=link.ordinal,
        target=link.target,
        type=link.type,
        declared_in=link.declared_in,
        element=link.element,
        attribute=link.attribute,
        anchor_text=None if attributes is None else attributes.anchor_text,
        alt_text=None if attributes is None else attributes.alt_text,
        rel=" ".join(link.rel) or None,
        rel_nofollow="nofollow" in link.rel,
        rel_ugc="ugc" in link.rel,
        rel_sponsored="sponsored" in link.rel,
    )
