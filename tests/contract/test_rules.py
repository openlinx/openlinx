"""The Rule tables in spider schema (040-add-rules, rules; seam 6)."""

import pytest
from sqlalchemy import Column, Text, select

from spider.store.schema import metadata, public_view, rules
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


def test_issues_is_a_view() -> None:
    result = run_cli("schema", "issues", "--fields", "name,kind")

    assert result.json()["items"] == [{"name": "issues", "kind": "view"}]


def test_a_view_that_declares_other_columns_than_its_query_is_refused() -> None:
    with pytest.raises(TypeError, match="declares other columns"):
        public_view(
            "rule_ids",
            Column("rule", Text, nullable=False, comment="A Rule id."),
            query=select(rules.c.id),
            comment="The Rule ids.",
            change=40,
        )

    assert "rule_ids" not in metadata.tables


def test_keys_of_the_rule_tables() -> None:
    keys = {}
    for table in ("rules", "affected_urls"):
        (item,) = run_cli("schema", table).json()["items"]
        keys[table] = [
            (column["name"], column["type"], column["references"])
            for column in item["columns"]
            if column["primary_key"]
        ]

    assert keys == {
        "rules": [("id", "TEXT", None)],
        "affected_urls": [("rule_id", "TEXT", "rules.id"), ("url_id", "INTEGER", "urls.id")],
    }


def test_indexes_of_affected_urls() -> None:
    (item,) = run_cli("schema", "affected_urls", "--fields", "indexes").json()["items"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")}
        for index in item["indexes"]
    ]

    assert {
        "name": "affected_urls_url_id",
        "columns": ["url_id"],
        "unique": False,
        "where": None,
    } in (reduced)


def test_issue_types_are_an_enumeration() -> None:
    (item,) = run_cli("schema", "issues").json()["items"]
    columns = {column["name"]: column for column in item["columns"]}

    assert columns["issue_type"]["values"] == ["issue", "warning", "opportunity"]
