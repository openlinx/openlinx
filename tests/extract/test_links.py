"""Link attributes (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_link_rows


def test_hyperlink_with_rel_flags() -> None:
    (row,) = page_link_rows(
        '<main><a href="/b" rel="nofollow UGC">Read  more</a></main>', url="https://example.test/a"
    )

    assert (
        row.type,
        row.target,
        row.anchor_text,
        row.rel,
        row.rel_nofollow,
        row.rel_ugc,
        row.rel_sponsored,
        row.declared_in,
    ) == (
        "hyperlink",
        "https://example.test/b",
        "Read more",
        "nofollow ugc",
        True,
        True,
        False,
        "body",
    )


def test_image_alt_attribute_absent_or_empty() -> None:
    rows = page_link_rows('<img src="/a.png"><img src="/b.png" alt="">')

    assert [(row.target, row.element, row.attribute, row.alt_text) for row in rows] == [
        ("https://site.test/a.png", "img", "src", None),
        ("https://site.test/b.png", "img", "src", ""),
    ]
