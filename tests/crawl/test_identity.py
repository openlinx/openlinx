"""What every request says about the tool (022-add-fetch-policy, fetching; seam 3)."""

import re

from spider.naming import APP_NAME
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.crawling import crawled
from tests.support.workspace import TempWorkspace

SHOP = Site(
    {
        "/robots.txt": Robots("User-agent: *\nDisallow: /cart\n"),
        "/": Page(body='<title>Shop</title><a href="/shoes">Shoes</a>'),
        "/shoes": Page(body="<title>Shoes</title>"),
    }
)


def test_the_default_user_agent_identifies_the_tool(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SHOP)

    crawled(server.url("/"))

    agents = {request.path: request.headers.get("User-Agent", "") for request in server.requests}
    assert sorted(agents) == ["/", "/robots.txt", "/shoes"]
    assert [
        path
        for path, agent in agents.items()
        if not re.fullmatch(rf"{APP_NAME}/\d+\.\d+\.\d+\S* \(\+https://\S+\)", agent)
    ] == []
