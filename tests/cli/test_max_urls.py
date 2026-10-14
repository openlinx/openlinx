"""The URL limit at the CLI (020-add-crawl-core D10, crawling; seam 1)."""

from tests.fixture_site.plugin import StartSite
from tests.support.cli import run_cli
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
