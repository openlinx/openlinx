"""Invalid settings name the offending key (010-add-workspace-and-cli-contract, workspace)."""

from pathlib import Path

from tests.support.app import example_app
from tests.support.cli import run_cli


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
