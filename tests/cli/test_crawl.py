"""`spider crawl` (020-add-crawl-core, crawling)."""

from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


def test_an_invalid_seed_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://exa mple.test/")
    errors = [line["code"] for line in result.stderr_json_lines() if line.get("level") == "error"]

    assert (result.exit_code, errors, list(temp_workspace.home.rglob("*.sqlite"))) == (
        2,
        ["invalid_url"],
        [],
    )


def test_a_seed_with_userinfo_is_rejected_with_a_hint_about_auth(
    temp_workspace: TempWorkspace,
) -> None:
    error = run_cli("crawl", "https://alice:s3cret@site.test/").stderr_json_lines()[-1]

    assert (error["code"], "--auth" in error["hint"], "s3cret" in error["message"]) == (
        "invalid_url",
        True,
        False,
    )
