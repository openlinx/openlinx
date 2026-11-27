"""Verify invalid settings name the offending key."""

from pathlib import Path

import pytest

from tests.support.app import example_app
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


def test_invalid_value(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b'[example]\nlevel = "medium"\n')

    result = run_cli("init", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        error["details"]["file"],
        error["details"]["errors"][0]["key"],
    ) == (3, "settings_invalid", str(shop / "openlinx.toml"), "example.level")


def test_unknown_key_with_a_suggestion(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b'[example]\nlevl = "high"\n')

    error = run_cli("init", app=example_app()).stderr_json_lines()[-1]

    assert (error["details"]["errors"][0]["key"], "level" in (error["hint"] or "")) == (
        "example.levl",
        True,
    )


def test_unknown_key_in_a_named_entry(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b'[groups.blog]\nlevl = "high"\n')

    error = run_cli("init", app=example_app()).stderr_json_lines()[-1]

    assert (error["details"]["errors"][0]["key"], "level" in (error["hint"] or "")) == (
        "groups.blog.levl",
        True,
    )


def test_a_setting_suggestion_uses_the_aliased_table_name(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[rules.title-too-long]\nmax_char = 70\n")

    result = run_cli("init")
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert error["details"]["errors"][0]["key"] == "rules.title-too-long.max_char"
    assert error["hint"] == "Did you mean rules.title-too-long.max_chars?"


def test_output_flags_have_no_settings_key(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b'[output]\nformat = "table"\n')

    result = run_cli("init", app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["details"]["errors"][0]["key"]) == (
        3,
        "settings_invalid",
        "output",
    )


def test_toml_syntax_error(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[example\n")

    first = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"][0]

    assert (first["key"], first["line"]) == (None, 1)


def test_every_problem_is_listed(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[example]\nlevel = 1\n[crawler]\n")

    errors = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"]

    assert [error["key"] for error in errors] == ["example.level", "crawler"]


def test_problems_are_listed_in_file_order(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[crawler]\n[example]\nlevel = 1\n")

    errors = run_cli("init", app=example_app()).stderr_json_lines()[-1]["details"]["errors"]

    assert [error["key"] for error in errors] == ["crawler", "example.level"]


def test_nothing_is_created_when_the_settings_are_invalid(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[example\n")

    run_cli("init", app=example_app())

    assert (shop / ".openlinx").exists() is False


def test_commands_without_a_workspace_ignore_the_settings_file(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b"[example\n")

    assert run_cli("commands", app=example_app()).exit_code == 0


def test_a_settings_file_that_is_not_utf8_is_invalid(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(b'[example]\nlevel = "\xff"\n')

    result = run_cli("init", app=example_app())

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (3, "settings_invalid")


def test_a_settings_file_that_is_a_folder_is_invalid_and_nothing_is_created(shop: Path) -> None:
    (shop / "openlinx.toml").mkdir()

    result = run_cli("init", app=example_app())

    assert (result.exit_code, (shop / ".openlinx").exists()) == (3, False)


def test_interleaved_rule_settings_keep_their_file_order(shop: Path) -> None:
    (shop / "openlinx.toml").write_text(
        """[rules]
"title-too-long".max_chars = -1
'h1-missing' . enabled = "off"
title-too-long."enabled" = 0
""",
        encoding="utf-8",
    )

    result = run_cli("rules", "list")
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "rules.title-too-long.max_chars",
        "rules.h1-missing.enabled",
        "rules.title-too-long.enabled",
    ]


def test_problem_order_uses_toml_key_parts_and_parents(shop: Path) -> None:
    (shop / "openlinx.toml").write_text(
        """crawl.concurrency = 0
"crawl.header" = 1
store.journal_mode = "invalid"
crawl.header = [42]
unknown.child = 1
crawl.max_urls = -1
""",
        encoding="utf-8",
    )

    result = run_cli("init")
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "crawl.concurrency",
        "crawl.header",
        "store.journal_mode",
        "crawl.header.0",
        "unknown",
        "crawl.max_urls",
    ]


def test_inline_rule_keys_keep_their_order_around_a_multiline_string(shop: Path) -> None:
    (shop / "openlinx.toml").write_text(
        '''example.token = """Text resembling settings:
[rules]
h1-missing.enabled = true # part of the string"""
rules = {title-too-long.enabled = 1, 'h1-missing'.enabled = 1, title-too-long.max_chars = -1}
''',
        encoding="utf-8",
    )

    result = run_cli("init", app=example_app())
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "rules.title-too-long.enabled",
        "rules.h1-missing.enabled",
        "rules.title-too-long.max_chars",
    ]


def test_array_table_item_problems_keep_their_header_positions(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(
        b"[[crawl.header]]\n[store]\njournal_mode = 'invalid'\n[[crawl.header]]\n"
    )

    result = run_cli("init")
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "crawl.header.0",
        "store.journal_mode",
        "crawl.header.1",
    ]


def test_error_positions_use_the_spelling_that_supplied_a_root_table(shop: Path) -> None:
    (shop / "openlinx.toml").write_bytes(
        b"CRAWL.concurrency = 0\n"
        b"crawl.max_urls = 20\n"
        b"store.journal_mode = 'invalid'\n"
        b"CRAWL.max_urls = -1\n"
    )

    result = run_cli("init")
    (error,) = result.stderr_json_lines()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "crawl.concurrency",
        "store.journal_mode",
        "crawl.max_urls",
    ]


def test_threshold_overflow_is_listed_with_other_settings_errors(shop: Path) -> None:
    too_large = "1" + "0" * 4300
    (shop / "openlinx.toml").write_text(
        "crawl.concurrency = 0\n"
        f'RULES = {{"title-too-long".max_chars = {too_large}}}\n'
        "crawl.max_urls = -1\n",
        encoding="utf-8",
    )

    result = run_cli("init")
    (error,) = result.errors()

    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert [problem["key"] for problem in error["details"]["errors"]] == [
        "crawl.concurrency",
        "rules.title-too-long.max_chars",
        "crawl.max_urls",
    ]


@pytest.mark.parametrize(
    ("source", "line"),
    [
        pytest.param("rules.title-too-long.max_chars = {value}\n[store", 2, id="unfinished-table"),
        pytest.param(
            "rules.title-too-long.max_chars = {value}\nrules.title-too-long.max_chars = 70",
            2,
            id="duplicate-key",
        ),
        pytest.param(
            "rules.title-too-long.max_chars = {value}\ninvalid = ]", 2, id="invalid-value"
        ),
        pytest.param("rules.title-too-long.max_chars = {value}\n= 1", 2, id="missing-key"),
        pytest.param(
            "rules = {{title-too-long.max_chars = {value} h1-missing.enabled=false}}",
            1,
            id="missing-comma",
        ),
        pytest.param("rules.title-too-long.max_chars = {value} junk", 1, id="trailing-token"),
    ],
)
def test_toml_syntax_error_after_an_overflowing_threshold(
    shop: Path, source: str, line: int
) -> None:
    settings_file = shop / "openlinx.toml"
    for value in ("70", f"{10**4300:#x}", "1" + "0" * 4300):
        settings_file.write_text(source.format(value=value) + "\n", encoding="utf-8")

        result = run_cli("init")
        (error,) = result.errors()

        assert (result.exit_code, error["code"]) == (3, "settings_invalid")
        assert error["details"]["file"] == str(settings_file.resolve())
        (problem,) = error["details"]["errors"]
        assert (problem["key"], problem["line"]) == (None, line)


def test_preview_and_active_rule_errors_keep_toml_order(temp_workspace: TempWorkspace) -> None:
    settings_file = temp_workspace.root / "openlinx.toml"
    source = (
        "rules.title-missing.enabled = 1\n"
        "rules.low-word-count.enabled = false\n"
        "rules.h1-missing.max_chars = 10\n"
        f"rules.title-too-long.max_chars = {10**4300:#x}\n"
        "rules.title-to-long.max_chars = 10\n"
    )
    settings_file.write_text(source, encoding="utf-8")
    both = run_cli("rules", "list")
    settings_file.write_text(
        source.replace("rules.low-word-count.enabled = false\n", ""), encoding="utf-8"
    )
    active = run_cli("rules", "list")

    assert both.exit_code == active.exit_code == 3
    (error,) = both.errors()
    assert error["code"] == "settings_invalid"
    errors = error["details"]["errors"]
    assert [problem["key"] for problem in errors] == [
        "rules.title-missing.enabled",
        "rules.low-word-count.enabled",
        "rules.h1-missing.max_chars",
        "rules.title-too-long.max_chars",
        "rules.title-to-long",
    ]
    (active_error,) = active.errors()
    assert errors[:1] + errors[2:] == active_error["details"]["errors"]
    assert error["hint"] == active_error["hint"]


@pytest.mark.parametrize(
    ("source", "keys"),
    [
        pytest.param(
            '[rules.low-word-count]\n"min.words" = 30\nmin.words = 31\n',
            ['rules.low-word-count."min.words"', "rules.low-word-count.min.words"],
            id="literal-dot-and-dotted-key",
        ),
        pytest.param(
            r"""rules.low-word-count = { nested = { "min\u002Ewords" = 30, '' = 31, """
            r"""'with space' = 32, "say\"\\\u007F😀" = 33 } }""",
            [
                'rules.low-word-count.nested."min.words"',
                'rules.low-word-count.nested.""',
                'rules.low-word-count.nested."with space"',
                r'rules.low-word-count.nested."say\"\\\u007f😀"',
            ],
            id="nested-inline-keys",
        ),
    ],
)
def test_preview_error_paths_identify_exact_toml_keys(
    temp_workspace: TempWorkspace, source: str, keys: list[str]
) -> None:
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_text(source + "\n", encoding="utf-8")

    result = run_cli("rules", "list")

    (error,) = result.errors()
    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert error["details"]["file"] == str(settings_file)
    assert error["details"]["errors"] == [
        {
            "key": key,
            "message": f"Remove {key} from the settings file. This Rule is deferred to v0.2.",
        }
        for key in keys
    ]


def test_deeply_nested_preview_setting_returns_its_full_path(
    temp_workspace: TempWorkspace,
) -> None:
    key = "rules.low-word-count." + "nested." * 980 + '"literal.dot"'
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_text(
        f"{key} = 30\nrules.low-word-count.enabled = false\n", encoding="utf-8"
    )

    result = run_cli("rules", "list")

    (error,) = result.errors()
    assert (result.exit_code, error["code"]) == (3, "settings_invalid")
    assert error["details"]["file"] == str(settings_file)
    assert error["details"]["errors"] == [
        {
            "key": path,
            "message": f"Remove {path} from the settings file. This Rule is deferred to v0.2.",
        }
        for path in (key, "rules.low-word-count.enabled")
    ]
