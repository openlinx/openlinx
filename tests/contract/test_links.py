"""The links table in linx schema (030-add-page-data, page-data; seam 6)."""

from typing import Any

from tests.support.cli import run_cli


def _values() -> dict[str, Any]:
    columns = run_cli("schema", "links").json()["items"][0]["columns"]
    return {column["name"]: column["values"] for column in columns}


def test_link_types_are_an_enumeration() -> None:
    assert _values()["type"] == [
        "hyperlink",
        "canonical",
        "pagination",
        "hreflang",
        "iframe",
        "meta_refresh",
        "http_refresh",
        "image",
        "css",
        "javascript",
        "video",
        "audio",
        "media",
        "amphtml",
        "mobile_alternate",
        "misc",
        "xml_sitemap",
        "sitemap_hreflang",
        "javascript_redirect",
    ]


def test_link_elements_and_attributes_are_enumerations() -> None:
    values = _values()

    assert (values["element"], values["attribute"]) == (
        [
            "a",
            "area",
            "link",
            "iframe",
            "frame",
            "meta",
            "img",
            "source",
            "video",
            "audio",
            "track",
            "embed",
            "object",
            "script",
        ],
        ["href", "src", "srcset", "poster", "data", "content"],
    )


def test_columns_of_links() -> None:
    columns = run_cli("schema", "links").json()["items"][0]["columns"]

    assert {(column["name"], column["type"], column["nullable"]) for column in columns} == {
        ("source_url_id", "INTEGER", False),
        ("ordinal", "INTEGER", False),
        ("target_url_id", "INTEGER", False),
        ("type", "TEXT", False),
        ("declared_in", "TEXT", False),
        ("element", "TEXT", True),
        ("attribute", "TEXT", True),
        ("anchor_text", "TEXT", True),
        ("alt_text", "TEXT", True),
        ("rel", "TEXT", True),
        ("rel_nofollow", "INTEGER", False),
        ("rel_ugc", "INTEGER", False),
        ("rel_sponsored", "INTEGER", False),
        ("followed", "INTEGER", False),
        ("hreflang", "TEXT", True),
        ("media", "TEXT", True),
        ("link_position", "TEXT", True),
        ("html_source", "TEXT", True),
    }
