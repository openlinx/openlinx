"""Link declarations, discovery policy and docs agree (030 D4; 023 D12; seam 6)."""

from pathlib import Path
from typing import Any

from openlinx.store.records import LINK_TYPES
from tests.support.cli import run_cli

CRAWLING_DOC = Path(__file__).resolve().parents[2] / "docs" / "crawling.md"


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


def test_link_type_table_matches_the_docs() -> None:
    _, heading, section = CRAWLING_DOC.read_text(encoding="utf-8").partition("### Link types\n")
    assert heading, "Link type docs must be present: restore the Link types section"
    section = section.split("\n### ", 1)[0]
    rows = [line.strip() for line in section.splitlines() if line.startswith("|")]
    assert rows[:2] == ["| Link type | Found in | Requested |", "|---|---|---|"], (
        "Link type docs must have their three columns: restore the Link types table header"
    )
    values = {"yes": "followed", "as a Resource": "resource", "no": None}
    documented: dict[str, str | None] = {}
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 3, f"Link type docs need three cells: fix {row}"
        name, _, requested = cells
        name = name.strip("`")
        assert name not in documented, f"Link type docs repeat {name}: keep one row per LinkType"
        assert requested in values, f"Requested cell is unknown: fix {name}'s {requested!r}"
        documented[name] = values[requested]
    # Later releases' types have no Requested row; their paragraph still names them.
    for name in ("xml_sitemap", "sitemap_hreflang", "javascript_redirect"):
        if name not in documented:
            assert f"`{name}`" in section, f"Link type docs omit {name}: restore its declaration"
            documented[name] = None

    assert documented == {name: info.requested for name, info in LINK_TYPES.items()}, (
        "Requested docs must match LINK_TYPES: fix missing/extra LinkTypes or their Requested cells"
    )
