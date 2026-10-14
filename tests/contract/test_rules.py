"""The Rule tables in spider schema (040-add-rules, rules; seam 6)."""

from tests.support.cli import run_cli


def test_categories_are_an_enumeration() -> None:
    (item,) = run_cli("schema", "rules").json()["items"]
    columns = {column["name"]: column for column in item["columns"]}

    assert columns["category"]["values"] == [
        "response_codes",
        "security",
        "titles",
        "meta_descriptions",
        "headings",
        "canonicals",
        "directives",
        "content",
        "urls",
        "images",
    ]
