"""Verify the public schema of the Rule tables."""

from tests.support.cli import run_cli


def test_keys_of_the_rule_tables() -> None:
    rules = run_cli("schema", "rules")
    affected_urls = run_cli("schema", "affected_urls")
    assert rules.exit_code == 0, rules.stderr
    assert affected_urls.exit_code == 0, affected_urls.stderr

    (rule_table,) = rules.json()["items"]
    (affected_table,) = affected_urls.json()["items"]
    assert {
        column["name"]: column["type"]
        for column in rule_table["columns"]
        if column["primary_key"] is True
    } == {"id": "TEXT"}
    assert {
        column["name"]: column["references"]
        for column in affected_table["columns"]
        if column["primary_key"] is True
    } == {"rule_id": "rules.id", "url_id": "urls.id"}


def test_indexes_of_affected_urls() -> None:
    result = run_cli("schema", "affected_urls", "--fields", "indexes")
    assert result.exit_code == 0, result.stderr
    (table,) = result.json()["items"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")}
        for index in table["indexes"]
    ]

    assert {
        "name": "affected_urls_url_id",
        "columns": ["url_id"],
        "unique": False,
        "where": None,
    } in reduced


def test_issue_types_are_an_enumeration() -> None:
    result = run_cli("schema", "issues")
    assert result.exit_code == 0, result.stderr

    (issues,) = result.json()["items"]
    (issue_type,) = (column for column in issues["columns"] if column["name"] == "issue_type")
    assert issue_type["values"] == ["issue", "warning", "opportunity"]
