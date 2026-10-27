"""What every request says about the tool (022-add-fetch-policy, fetching; seam 3)."""

import json
import re

import pytest

from spider.naming import SETTINGS_FILE_NAME
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result, crawled
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
        if not re.fullmatch(r"spider/\d+\.\d+\.\d+\S* \(\+https://\S+\)", agent)
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


# An empty header, a blank one that is empty on the wire, one that would add a header of its own,
# a bell from a pasted string, and names that go out as bytes outside ASCII, which servers and
# log pipelines misread.
_NOT_USER_AGENTS = [
    "",
    "   ",
    "AuditBot/1.0\r\nX-Forwarded-For: 10.0.0.1",
    "AuditBot\x07/1.0",
    "Мой бот/1.0",
    "Crawlér/2.0",
]


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


def test_cookies_set_by_the_site_are_not_sent_back(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    # On a named host: a cookie jar keeps no cookie of a bare IP address, so it would not show.
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body='<title>Shop</title><a href="/check">Check out</a>',
                    headers=[("Set-Cookie", "sid=abc123; Path=/; HttpOnly")],
                ),
                "/check": Page(body="<title>Check out</title>"),
            }
        ),
        Site({}),
    )

    crawl_result("http://site.test/", resolver=hosts.resolver)

    assert [(request.path, request.headers.get("Cookie")) for request in hosts.site.requests] == [
        ("/robots.txt", None),
        ("/", None),
        ("/check", None),
    ]
