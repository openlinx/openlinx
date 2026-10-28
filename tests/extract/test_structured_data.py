"""Structured-data counts and types (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_row


def test_json_ld_graph_a_broken_block_and_nested_microdata() -> None:
    # An SEO plugin's graph in head, a block a template broke, and a product with its offer.
    row = page_row(
        "<html><head><title>Shop</title>"
        '<script type="application/ld+json">{"@context":"https://schema.org","@graph":'
        '[{"@type":"Organization"},{"@type":"WebSite"}]}</script>'
        '<script type="application/ld+json">{bad json</script></head><body>'
        '<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">Kettle</h1>'
        '<span itemprop="offers" itemscope itemtype="https://schema.org/Offer"></span></div>'
        "</body></html>"
    )

    assert (
        row.jsonld_items,
        row.jsonld_parse_errors,
        row.microdata_items,
        row.structured_data_types,
    ) == (2, 1, 1, ("Organization", "Product", "WebSite"))


def _nested(levels: int) -> str:
    return f'<script type="application/ld+json">{"[" * levels}{"]" * levels}</script>'


def test_a_json_ld_block_nested_more_than_1024_levels_is_a_parse_error() -> None:
    row = page_row(_nested(1024) + _nested(1025) + _nested(100_000) + "<h1>Still read</h1>")

    assert (row.jsonld_parse_errors, row.h1_1) == (2, "Still read")
