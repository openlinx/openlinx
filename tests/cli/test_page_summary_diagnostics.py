"""Check the recovery information for refused Page and Summary arguments."""

import re

import pytest

from tests.support.cli import run_cli

_RECOMMENDED_FORMAT = re.compile(
    r"(?:for --format,? )?(?:use|choose|select|specify|pass) "
    r"(?:--format (?:with (?:one of: )?)?)?(?:either )?"
    r"(?:json(?:, | or | and )table|table(?:, | or | and )json)(?: (?:for|with) --format)?\.?",
    re.IGNORECASE,
)
_TOP_RANGE = re.compile(
    r"(?:for --top,? )?(?:use|choose|select|specify|pass) (?:--top with )?"
    r"(?:an? )?(?:integer|whole number) (?:from 0 to 100|between 0 and 100)(?: inclusive)?"
    r"(?: for --top)?\.?",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    ("args", "message_part", "command"),
    [
        (("page",), "url", "page"),
        (("summary", "--top"), "--top", "summary"),
        (("summary", "--typo"), "--typo", "summary"),
    ],
)
def test_usage_error_points_to_command_help(
    args: tuple[str, ...], message_part: str, command: str
) -> None:
    result = run_cli(*args)

    assert (result.exit_code, result.stdout) == (2, b"")
    error = result.errors()[-1]
    assert error["code"] == "usage_error"
    assert message_part in error["message"].casefold()
    assert f"linx {command} --help" in (error["hint"] or "")


@pytest.mark.parametrize(
    ("args", "accepted"),
    [
        (("page", "https://example.com/", "--format", "csv"), ["json", "table"]),
        (("summary", "--format", "csv"), ["json", "table"]),
        (("summary", "--format", "jsonl"), ["json", "table"]),
    ],
)
def test_format_choice_lists_all_available_formats(
    args: tuple[str, ...], accepted: list[str]
) -> None:
    result = run_cli(*args)

    assert (result.exit_code, result.stdout) == (2, b"")
    error = result.errors()[-1]
    assert error["code"] == "invalid_value"
    assert error["details"].get("accepted") == accepted
    assert "--format" in error["hint"]
    assert _RECOMMENDED_FORMAT.fullmatch(error["hint"]), error["hint"]


@pytest.mark.parametrize("value", ["-1", "101"])
def test_summary_top_out_of_range_gives_both_bounds(value: str) -> None:
    result = run_cli("summary", "--top", value)

    assert (result.exit_code, result.stdout) == (2, b"")
    error = result.errors()[-1]
    assert error["code"] == "invalid_value"
    assert "--top" in error["hint"]
    assert _TOP_RANGE.fullmatch(error["hint"]), error["hint"]
