"""Output formats (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.cli import run_cli


def test_unsupported_format_is_an_invalid_value_whose_hint_lists_the_formats() -> None:
    result = run_cli("commands", "--format", "csv")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], "json" in error["hint"], "table" in error["hint"]) == (
        2,
        "invalid_value",
        True,
        True,
    )
