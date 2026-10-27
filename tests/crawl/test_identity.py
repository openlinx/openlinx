"""What every request says about the tool (022-add-fetch-policy, fetching; seam 3)."""

import json
import re

import pytest

from spider.naming import APP_NAME, SETTINGS_FILE_NAME
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.cli import run_cli
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


def test_a_custom_user_agent_is_used_on_every_request(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SHOP)

    crawled(server.url("/"), "--user-agent", "AuditBot/1.0")

    assert {request.path: request.headers.get("User-Agent") for request in server.requests} == {
        "/robots.txt": "AuditBot/1.0",
        "/": "AuditBot/1.0",
        "/shoes": "AuditBot/1.0",
    }


# An empty header, one that would add a header of its own, and a bell from a pasted string.
_NOT_USER_AGENTS = ["", "AuditBot/1.0\r\nX-Forwarded-For: 10.0.0.1", "AuditBot\x07/1.0"]


@pytest.mark.parametrize("user_agent", _NOT_USER_AGENTS)
def test_an_invalid_user_agent_is_rejected(
    temp_workspace: TempWorkspace, fixture_site: StartSite, user_agent: str
) -> None:
    server = fixture_site(SHOP)

    result = run_cli("crawl", server.url("/"), "--user-agent", user_agent)

    assert (
        result.exit_code,
        [(error["code"], "--user-agent" in error["message"]) for error in result.errors()],
        server.requests,
    ) == (2, [("invalid_value", True)], ())


@pytest.mark.parametrize("user_agent", _NOT_USER_AGENTS)
def test_an_invalid_user_agent_in_the_settings_file_is_refused(
    temp_workspace: TempWorkspace, user_agent: str
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(
        f"[crawl]\nuser_agent = {json.dumps(user_agent)}\n".encode()
    )

    result = run_cli("crawl", "http://site.test/")

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
    ) == (3, [("settings_invalid", "crawl.user_agent")])
