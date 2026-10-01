"""Output formats (010-add-workspace-and-cli-contract, cli-contract)."""

from pathlib import Path

from tests.support.cli import run_cli


def test_unsupported_format_is_an_invalid_value_whose_hint_lists_the_formats() -> None:
    result = run_cli("commands", "--format", "jsonl")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], "json" in error["hint"], "table" in error["hint"]) == (
        2,
        "invalid_value",
        True,
        True,
    )


def test_table_for_people(shop: Path) -> None:
    stdout = run_cli("init", "--format", "table").stdout

    assert (b"data_dir" in stdout, stdout.startswith(b"{")) == (True, False)
