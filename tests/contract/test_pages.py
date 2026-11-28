"""Verify the pages table exposed by the schema Command."""

from typing import Any

from tests.support.cli import run_cli
from tests.support.page_data import LATER_PAGE_COLUMNS


def test_schema_lists_exactly_the_page_record_columns() -> None:
    columns = run_cli("schema", "pages").json()["items"][0]["columns"]

    assert {column["name"]: (column["type"], column["nullable"]) for column in columns} == {
        "url_id": ("INTEGER", False),
        "address": ("TEXT", False),
        "url_encoded_address": ("TEXT", False),
        "url_path": ("TEXT", False),
        "url_query": ("TEXT", True),
        "content_type": ("TEXT", False),
        "status_code": ("INTEGER", False),
        "status": ("TEXT", True),
        "indexability": ("TEXT", False),
        "indexability_status": ("TEXT", True),
        "response_time_ms": ("INTEGER", False),
        "last_modified": ("TEXT", True),
        "redirect_url": ("TEXT", True),
        "redirect_type": ("TEXT", True),
        "set_cookie_count": ("INTEGER", False),
        "js_cookie_count": ("INTEGER", True),
        "http_version": ("TEXT", True),
        "crawl_timestamp": ("TEXT", False),
        "title_1": ("TEXT", True),
        "title_1_length": ("INTEGER", True),
        "title_1_width_px": ("INTEGER", True),
        "title_2": ("TEXT", True),
        "title_2_length": ("INTEGER", True),
        "title_2_width_px": ("INTEGER", True),
        "title_count": ("INTEGER", True),
        "meta_description_1": ("TEXT", True),
        "meta_description_1_length": ("INTEGER", True),
        "meta_description_1_width_px": ("INTEGER", True),
        "meta_description_2": ("TEXT", True),
        "meta_description_2_length": ("INTEGER", True),
        "meta_description_2_width_px": ("INTEGER", True),
        "meta_description_count": ("INTEGER", True),
        "meta_keywords_1": ("TEXT", True),
        "meta_keywords_1_length": ("INTEGER", True),
        "h1_1": ("TEXT", True),
        "h1_1_length": ("INTEGER", True),
        "h1_2": ("TEXT", True),
        "h1_2_length": ("INTEGER", True),
        "h1_count": ("INTEGER", True),
        "h2_1": ("TEXT", True),
        "h2_1_length": ("INTEGER", True),
        "h2_2": ("TEXT", True),
        "h2_2_length": ("INTEGER", True),
        "h2_count": ("INTEGER", True),
        "meta_robots": ("TEXT", True),
        "meta_robots_noindex": ("INTEGER", True),
        "meta_robots_nofollow": ("INTEGER", True),
        "x_robots_tag": ("TEXT", True),
        "x_robots_tag_noindex": ("INTEGER", True),
        "x_robots_tag_nofollow": ("INTEGER", True),
        "meta_refresh": ("TEXT", True),
        "canonical_url": ("TEXT", True),
        "canonical_link_element_1": ("TEXT", True),
        "canonical_link_element_2": ("TEXT", True),
        "http_canonical": ("TEXT", True),
        "canonical_count": ("INTEGER", True),
        "canonical_relative": ("INTEGER", True),
        "rel_next_1": ("TEXT", True),
        "rel_prev_1": ("TEXT", True),
        "http_rel_next_1": ("TEXT", True),
        "http_rel_prev_1": ("TEXT", True),
        "amphtml_link_element": ("TEXT", True),
        "mobile_alternate_link": ("TEXT", True),
        "size_bytes": ("INTEGER", True),
        "transferred_bytes": ("INTEGER", True),
        "content_encoding": ("TEXT", True),
        "word_count": ("INTEGER", True),
        "sentence_count": ("INTEGER", True),
        "average_words_per_sentence": ("REAL", True),
        "syllable_count": ("INTEGER", True),
        "flesch_reading_ease": ("REAL", True),
        "readability": ("TEXT", True),
        "text_ratio_pct": ("REAL", True),
        "declared_language": ("TEXT", True),
        "detected_language": ("TEXT", True),
        "content_hash": ("TEXT", True),
        "closest_similarity_pct": ("REAL", True),
        "near_duplicate_count": ("INTEGER", True),
        "crawl_depth": ("INTEGER", False),
        "folder_depth": ("INTEGER", False),
        "link_score": ("REAL", True),
        "inlinks": ("INTEGER", True),
        "unique_inlinks": ("INTEGER", True),
        "unique_js_inlinks": ("INTEGER", True),
        "linking_pages_pct": ("REAL", True),
        "outlinks": ("INTEGER", True),
        "unique_outlinks": ("INTEGER", True),
        "unique_js_outlinks": ("INTEGER", True),
        "external_outlinks": ("INTEGER", True),
        "unique_external_outlinks": ("INTEGER", True),
        "jsonld_item_count": ("INTEGER", True),
        "microdata_item_count": ("INTEGER", True),
        "jsonld_parse_error_count": ("INTEGER", True),
        "structured_data_types": ("TEXT", True),
        "structured_data_error_count": ("INTEGER", True),
        "structured_data_warning_count": ("INTEGER", True),
    }


def test_indexes_of_pages() -> None:
    indexes = run_cli("schema", "pages", "--fields", "indexes").json()["items"][0]["indexes"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")} for index in indexes
    ]

    assert {"name": "pages_address", "columns": ["address"], "unique": True, "where": None} in (
        reduced
    )


def test_inlink_columns_are_derived() -> None:
    columns = run_cli("schema", "pages").json()["items"][0]["columns"]
    descriptions = {column["name"]: column["description"] for column in columns}

    assert {
        name: descriptions[name][: len("Derived: ")]
        for name in ("inlinks", "unique_inlinks", "linking_pages_pct")
    } == dict.fromkeys(("inlinks", "unique_inlinks", "linking_pages_pct"), "Derived: ")


def _columns(table: str) -> dict[str, dict[str, Any]]:
    columns = run_cli("schema", table).json()["items"][0]["columns"]
    return {column["name"]: column for column in columns}


def test_redirect_url_describes_how_meta_refresh_selects_its_target() -> None:
    description = _columns("pages")["redirect_url"]["description"]

    assert (
        "If the Page extractor fails (urls.parse_error is extractor_error), "
        "meta_refresh is NULL and the first discovered meta refresh Link can supply redirect_url."
    ) in description
    assert (
        "For meta refresh after successful Page extraction, the first declaration "
        "must contain a URL reference. "
        "The first resolved meta refresh Link supplies the target, which can come "
        "from a later declaration if the first reference cannot be resolved."
    ) in description


def test_deferred_columns_are_described_with_their_release() -> None:
    # Every later column, not only the spec's three, so a wrong release anywhere fails.
    pages, links = _columns("pages"), _columns("links")
    columns = {f"pages.{name}": pages.get(name) for name in LATER_PAGE_COLUMNS}
    columns["links.html_source"] = links.get("html_source")
    expected = {f"pages.{name}": f"Filled from {r}. " for name, r in LATER_PAGE_COLUMNS.items()}
    expected["links.html_source"] = "Filled from v1.1. "

    assert {
        key: column and column["description"][: len(expected[key])]
        for key, column in columns.items()
    } == expected


def test_structured_data_validation_counts_are_deferred_integer_columns() -> None:
    columns = _columns("pages")
    names = (
        "structured_data_error_count",
        "structured_data_warning_count",
        "structured_data_errors",
        "structured_data_warnings",
    )

    assert {
        name: (
            column["type"],
            column["nullable"],
            column["description"][: len("Filled from v0.3. ")],
        )
        for name in names
        if (column := columns.get(name)) is not None
    } == {
        "structured_data_error_count": ("INTEGER", True, "Filled from v0.3. "),
        "structured_data_warning_count": ("INTEGER", True, "Filled from v0.3. "),
    }


def test_later_enumerations_list_their_values() -> None:
    pages, links = _columns("pages"), _columns("links")

    assert (
        pages.get("readability", {}).get("values"),
        pages.get("http_version", {}).get("values"),
        links.get("html_source", {}).get("values"),
    ) == (
        [
            "very_easy",
            "easy",
            "fairly_easy",
            "normal",
            "fairly_difficult",
            "difficult",
            "very_difficult",
        ],
        ["http_2", "http_1_1"],
        ["raw", "rendered"],
    )
