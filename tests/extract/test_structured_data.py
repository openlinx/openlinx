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
        row.jsonld_item_count,
        row.jsonld_parse_error_count,
        row.microdata_item_count,
        row.structured_data_types,
    ) == (2, 1, 1, ("Organization", "Product", "WebSite"))


def test_json_ld_array_type_lists_and_an_http_type() -> None:
    # A news theme's array, a breadcrumb plugin's single-object graph, a template that left
    # its type empty, and an article marked up as two types.
    row = page_row(
        "<html><head><title>News</title>"
        '<script type=" Application/LD+JSON ">[{"@type":["Article","NewsArticle"]},'
        '{"@graph":[{"@type":"http://schema.org/Person"},{"@type":"Article"}]},"note"]</script>'
        '<script type="application/ld+json">{"@context":"https://schema.org",'
        '"@graph":{"@type":"BreadcrumbList"}}</script>'
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":""}'
        "</script></head><body>"
        '<article itemscope itemtype="https://schema.org/Article https://schema.org/BlogPosting">'
        "<p>Story</p></article></body></html>"
    )

    assert (
        row.jsonld_item_count,
        row.jsonld_parse_error_count,
        row.microdata_item_count,
        row.structured_data_types,
    ) == (5, 0, 1, ("Article", "BlogPosting", "BreadcrumbList", "NewsArticle", "Person"))


def test_page_without_structured_data() -> None:
    row = page_row(
        "<html><head><title>About</title><script>var page = {};</script></head>"
        "<body><h1>About us</h1><p>We make kettles.</p></body></html>"
    )

    counts = (row.jsonld_item_count, row.microdata_item_count, row.structured_data_types)

    assert counts == (0, 0, ())


def test_a_type_that_is_only_the_schema_org_prefix_is_skipped() -> None:
    # Templates that render the type into a schema.org URL and had no type to render.
    row = page_row(
        '<script type="application/ld+json">{"@type":"http://schema.org/"}</script>'
        '<div itemscope itemtype="https://schema.org/"><p>Item</p></div>'
    )

    counts = (row.jsonld_item_count, row.microdata_item_count, row.structured_data_types)

    assert counts == (1, 1, ())


def test_a_number_beyond_a_double_and_an_unpaired_surrogate_are_parse_errors() -> None:
    # A measurement written out of range, and a description cut to a length limit in the
    # middle of an emoji's surrogate pair.
    row = page_row(
        '<script type="application/ld+json">{"@type":"Product","weight":1e400}</script>'
        '<script type="application/ld+json">{"@type":"Review","description":"Great \\ud83d"}'
        '</script><script type="application/ld+json">{"@type":"Thing"}</script>'
    )

    assert (
        row.jsonld_item_count,
        row.jsonld_parse_error_count,
        row.structured_data_types,
    ) == (1, 2, ("Thing",))


def _nested(levels: int) -> str:
    return f'<script type="application/ld+json">{"[" * levels}{"]" * levels}</script>'


def test_a_json_ld_block_nested_more_than_1024_levels_is_a_parse_error() -> None:
    row = page_row(_nested(1024) + _nested(1025) + _nested(100_000) + "<h1>Still read</h1>")

    assert (row.jsonld_parse_error_count, row.h1_1) == (2, "Still read")
