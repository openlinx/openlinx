"""The --crawl flag (015-add-crawl-store, crawl-store)."""

from tests.support.app import EXAMPLE_READ_CRAWL, example_app
from tests.support.cli import run_cli
from tests.support.crawls import create_crawl_at
from tests.support.workspace import TempWorkspace


def test_the_flag_defaults_to_latest(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")
    create_crawl_at(temp_workspace, "2026-09-27T11:00:00.000Z", "bbbb")

    result = run_cli(EXAMPLE_READ_CRAWL, app=example_app())

    assert (result.exit_code, result.json()) == (0, {"crawl": "20260927-110000-bbbb"})


def test_the_flag_is_described_as_global() -> None:
    entry = next(
        command
        for command in run_cli("commands", app=example_app()).json()["commands"]
        if command["name"] == EXAMPLE_READ_CRAWL
    )
    option = next(option for option in entry["options"] if option["name"] == "--crawl")

    assert (option["global"], option["default"]) == (True, "latest")


def test_unknown_id_on_the_command_line(temp_workspace: TempWorkspace) -> None:
    create_crawl_at(temp_workspace, "2026-09-27T10:00:00.000Z", "aaaa")

    result = run_cli(EXAMPLE_READ_CRAWL, "--crawl", "20260101-000000-zzzz", app=example_app())

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (4, "crawl_not_found")


def test_no_crawls_on_the_command_line(temp_workspace: TempWorkspace) -> None:
    result = run_cli(EXAMPLE_READ_CRAWL, app=example_app())
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], "linx crawl" in error["hint"]) == (
        4,
        "no_crawls",
        True,
    )


def test_a_text_file_on_the_command_line(temp_workspace: TempWorkspace) -> None:
    notes = temp_workspace.root / "notes.sqlite"
    notes.write_text("hello", encoding="utf-8")

    result = run_cli(EXAMPLE_READ_CRAWL, "--crawl", str(notes), app=example_app())

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (6, "crawl_file_invalid")


def test_a_malformed_value_on_the_command_line(temp_workspace: TempWorkspace) -> None:
    result = run_cli(EXAMPLE_READ_CRAWL, "--crawl", "yesterday", app=example_app())

    assert (result.exit_code, result.stderr_json_lines()[-1]["code"]) == (2, "invalid_value")
