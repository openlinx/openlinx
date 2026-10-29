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
