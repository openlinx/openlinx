"""`spider rules` (040-add-rules, rules; seam 1)."""

from tests.support.cli import run_cli

GUIDANCE = ("description", "why_it_matters", "how_to_fix")


def test_first_rule_in_the_list() -> None:
    page = run_cli("rules", "list", "--limit", "1").json()

    assert (page["items"][0]["id"], page["items"][0]["category"], page["next_cursor"] is None) == (
        "internal-4xx",
        "response_codes",
        False,
    )


def test_every_rule_has_its_guidance() -> None:
    items = run_cli("rules", "list", "--limit", "50").json()["items"]

    assert [item["id"] for item in items if not all(item[key] for key in GUIDANCE)] == []


def test_show_a_rule_with_thresholds() -> None:
    result = run_cli("rules", "show", "title-too-long")
    rule = result.json()

    assert (
        result.exit_code,
        rule["category"],
        rule["issue_type"],
        rule["priority"],
        rule["thresholds"],
    ) == (
        0,
        "titles",
        "opportunity",
        "medium",
        {"max_chars": {"value": 60, "default": 60, "unit": "characters"}},
    )


def test_the_bare_group_lists_the_rules() -> None:
    assert run_cli("rules").json() == run_cli("rules", "list").json()
