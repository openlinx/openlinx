"""The URL limit at the CLI (020-add-crawl-core D10, crawling; seam 1)."""

import pytest

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

    document = result.json()
    assert [
        (warning["hint"], warning["details"]["max_urls"])
        for warning in document["warnings"]
        if warning["code"] == "max_urls_reached"
    ] == [(f"spider resume --crawl {document['crawl_id']} --max-urls 6", 3)]


def test_there_is_no_limit_by_default(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    document = run_cli("crawl", server.url("/")).json()

    assert (document["state"], document["urls"]["fetched"]) == ("completed", 10)


def test_a_limit_below_one_is_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--max-urls", "0")

    assert (result.exit_code, [error["code"] for error in result.errors()]) == (
        2,
        ["invalid_value"],
    )


def test_a_limit_below_one_in_the_settings_file_is_refused(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "spider.toml").write_bytes(b"[crawl]\nmax_urls = 0\n")

    result = run_cli("crawl", "http://site.test/")

    assert (result.exit_code, [error["code"] for error in result.errors()]) == (
        3,
        ["settings_invalid"],
    )


@pytest.mark.parametrize(
    ("max_urls", "state", "stop_reason"),
    [("10", "completed", None), ("9", "stopped", "max_urls")],
)
def test_the_limit_is_reached_only_when_it_refuses_a_request(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    max_urls: str,
    state: str,
    stop_reason: str | None,
) -> None:
    server = fixture_site(NINE_PAGES)

    document = run_cli("crawl", server.url("/"), "--max-urls", max_urls).json()

    assert (document["state"], document["stop_reason"]) == (state, stop_reason)
