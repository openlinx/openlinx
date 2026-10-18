"""`spider rules` (040-add-rules, rules; seam 1)."""

import json
import sys
from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli, run_cli_process
from tests.support.crawling import crawled
from tests.support.crawls import query

GUIDANCE = ("description", "why_it_matters", "how_to_fix")
HOME_PAGE = Site({"/": Page(body="<title>Home</title>")})


# spider rules reads the nearest Workspace, so a test never reads the one it runs in.
pytestmark = pytest.mark.usefixtures("shop")


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


# The Health Score counts the Pages of internal_pages, Indexable Pages among them.
APPLIES_TO = {
    "internal-4xx": "internal_urls",
    "internal-5xx": "internal_urls",
    "internal-no-response": "internal_urls",
    "internal-blocked-by-robots-txt": "internal_urls",
    "http-url": "internal_urls",
    "title-missing": "internal_pages",
    "title-duplicate": "internal_pages",
    "title-too-long": "internal_pages",
    "meta-description-missing": "internal_pages",
    "h1-missing": "internal_pages",
}


def test_every_rule_applies_to_its_population() -> None:
    items = run_cli("rules", "list", "--fields", "id,applies_to", "--limit", "50").json()["items"]

    assert {item["id"]: item["applies_to"] for item in items} == APPLIES_TO


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


def test_override_shown_by_the_rules_command(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")

    rule = run_cli("rules", "show", "title-too-long").json()

    assert rule["thresholds"]["max_chars"] == {"value": 70, "default": 60, "unit": "characters"}


def test_disabled_rule_is_listed(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.h1-missing]\nenabled = false\n")

    items = run_cli("rules", "list", "--limit", "50").json()["items"]

    assert [item["id"] for item in items if not item["enabled"]] == ["h1-missing"]


def test_misspelt_rule_id(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.title-to-long]\nmax_chars = 70\n")

    result = run_cli("rules", "list")
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        error["details"]["errors"][0]["key"],
        "title-too-long" in (error["hint"] or ""),
    ) == (3, "settings_invalid", "rules.title-to-long", True)


def test_a_rule_table_named_by_its_field_name_is_invalid(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.title_too_long]\nmax_chars = 70\n")

    result = run_cli("rules", "list")

    assert (result.exit_code, result.stderr_json_lines()[-1]["hint"]) == (
        3,
        "Did you mean rules.title-too-long?",
    )


def test_unknown_key(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.h1-missing]\nmax_chars = 10\n")

    result = run_cli("rules", "list")

    assert (result.exit_code, result.stderr_json_lines()[-1]["details"]["errors"][0]["key"]) == (
        3,
        "rules.h1-missing.max_chars",
    )


def test_a_misspelt_threshold_gets_the_closest_name(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_char = 70\n")

    error = run_cli("rules", "list").stderr_json_lines()[-1]

    assert error["hint"] == "Did you mean rules.title-too-long.max_chars?"


def test_negative_threshold(shop: Path, fixture_site: StartSite) -> None:
    server = fixture_site(HOME_PAGE)
    (shop / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = -5\n")

    result = run_cli("crawl", server.url("/"))

    assert (
        result.exit_code,
        result.stderr_json_lines()[-1]["details"]["errors"][0]["key"],
        len(server.requests),
    ) == (3, "rules.title-too-long.max_chars", 0)


def test_a_rule_setting_of_another_type_is_invalid(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(
        b'[rules.title-too-long]\nmax_chars = "70"\nenabled = "no"\n'
    )

    errors = run_cli("rules", "list").stderr_json_lines()[-1]["details"]["errors"]

    assert [error["key"] for error in errors] == [
        "rules.title-too-long.max_chars",
        "rules.title-too-long.enabled",
    ]


def test_rule_without_thresholds() -> None:
    items = run_cli("rules", "list", "--limit", "50").json()["items"]

    assert [item["thresholds"] for item in items if item["id"] == "title-missing"] == [{}]


def test_an_unknown_rule_id_gets_the_closest_ids() -> None:
    (error,) = run_cli("rules", "show", "title-mising").stderr_json_lines()

    assert error["details"]["suggestions"][0] == "title-missing"


def test_unknown_rule_id() -> None:
    result = run_cli("rules", "show", "nope")
    (error,) = result.stderr_json_lines()

    assert (
        result.exit_code,
        error["code"],
        "nope" in error["message"],
        "spider rules list" in error["hint"],
    ) == (4, "rule_not_found", True, True)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_windows_console_output() -> None:
    stdout = run_cli_process("rules", "show", "title-too-long").stdout

    # Byte for byte as in process: no line ending or encoding of the console's. 010's
    # Cyrillic tests guard the encoding itself, since a Rule's texts are ASCII.
    assert (json.loads(stdout.decode("utf-8"))["id"], stdout) == (
        "title-too-long",
        run_cli("rules", "show", "title-too-long").stdout,
    )


def test_the_bare_group_lists_the_rules() -> None:
    assert run_cli("rules").json() == run_cli("rules", "list").json()


def test_an_option_after_the_group_name_says_where_it_goes() -> None:
    result = run_cli("rules", "--limit", "1")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["hint"]) == (
        2,
        "usage_error",
        "Put --limit after the Command name: spider rules list --limit ...",
    )


def test_an_option_before_a_grouped_command_names_that_command() -> None:
    result = run_cli("rules", "--format", "table", "show", "title-too-long")

    assert result.stderr_json_lines()[-1]["hint"] == (
        "Put --format after the Command name: spider rules show --format ..."
    )


def test_a_root_option_after_a_group_name_gets_the_root_hint() -> None:
    result = run_cli("rules", "--version")

    assert result.stderr_json_lines()[-1]["hint"] == (
        "Put --version before the Command name: spider --version"
    )


def test_the_root_help_lists_the_group() -> None:
    result = run_cli("--help")

    assert (result.exit_code, b"rules" in result.stdout) == (0, True)


def test_the_group_help_lists_its_commands() -> None:
    result = run_cli("rules", "--help")

    assert (result.exit_code, b"list" in result.stdout, b"show" in result.stdout) == (
        0,
        True,
        True,
    )


def test_the_rules_of_another_workspace(shop: Path) -> None:
    other = shop.parent / "other"
    other.mkdir()
    (other / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")

    rule = run_cli("rules", "show", "title-too-long", "--workspace", str(other)).json()

    assert rule["thresholds"]["max_chars"]["value"] == 70


def test_a_threshold_above_the_integer_range_of_the_store_is_invalid(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 9223372036854775808\n")

    result = run_cli("rules", "list")

    assert (result.exit_code, result.stderr_json_lines()[-1]["details"]["errors"][0]["key"]) == (
        3,
        "rules.title-too-long.max_chars",
    )


def test_a_rule_id_in_capitals_gets_the_closest_id(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b"[rules.TITLE-TOO-LONG]\nmax_chars = 70\n")

    error = run_cli("rules", "list").stderr_json_lines()[-1]

    assert error["hint"] == "Did you mean rules.title-too-long?"


def test_the_rules_command_prints_the_reproducing_query(fixture_site: StartSite) -> None:
    crawl_file = crawled(fixture_site(HOME_PAGE).url("/"))

    shown = run_cli("rules", "show", "title-missing").json()["reproduce_sql"]

    assert [(shown,)] == query(
        crawl_file, "SELECT reproduce_sql FROM rules WHERE id = 'title-missing'"
    )
