"""What `spider crawl` reports about robots.txt (020-add-crawl-core D6, crawling; seam 1)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


def test_a_blocked_seed_is_reported(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Robots("User-agent: *\nDisallow: /\n"),
                "/": Page(body="<p>/</p>"),
            }
        )
    )

    result = run_cli("crawl", server.url("/"))

    assert [
        "--ignore-robots" in (warning["hint"] or "")
        for warning in result.json()["warnings"]
        if warning["code"] == "seed_blocked_by_robots_txt"
    ] == [True]
