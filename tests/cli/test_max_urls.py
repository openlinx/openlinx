"""The URL limit at the CLI (020-add-crawl-core D10, crawling; seam 1)."""

from tests.fixture_site.plugin import StartSite
from tests.support.cli import CliResult, run_cli
from tests.support.sites import NINE_PAGES
from tests.support.workspace import TempWorkspace


def test_the_crawl_stops_at_the_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    result = run_cli("crawl", server.url("/"), "--max-urls", "3")

    document = result.json()
    assert (
        result.exit_code,
        document["state"],
        document["stop_reason"],
        document["urls"]["fetched"],
    ) == (0, "stopped", "max_urls", 3)


def test_the_limit_warning_says_how_to_continue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    result = run_cli("crawl", server.url("/"), "--max-urls", "3")

    assert [
        "--max-urls" in (warning["hint"] or "")
        for warning in result.json()["warnings"]
        if warning["code"] == "max_urls_reached"
    ] == [True]


def test_there_is_no_limit_by_default(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    document = run_cli("crawl", server.url("/")).json()

    assert (document["state"], document["urls"]["fetched"]) == ("completed", 10)


def test_a_limit_below_one_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--max-urls", "0")

    assert (result.exit_code, _error_codes(result)) == (2, ["invalid_value"])


def test_a_limit_below_one_in_the_settings_file_is_refused(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "spider.toml").write_bytes(b"[crawl]\nmax_urls = 0\n")

    result = run_cli("crawl", "http://site.test/")

    assert (result.exit_code, _error_codes(result)) == (3, ["settings_invalid"])


def _error_codes(result: CliResult) -> list[str]:
    return [line["code"] for line in result.stderr_json_lines() if line.get("level") == "error"]
