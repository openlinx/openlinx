"""What `linx crawl` reports about robots.txt (020-add-crawl-core D6, crawling; seam 1)."""

import json
from pathlib import Path

import pytest

from openlinx.naming import DEFAULT_ROBOTS_TOKEN
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.crawls import crawl_row
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


def test_an_unreachable_robots_txt_of_the_site_is_reported(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/robots.txt": Status(503), "/": Page(body="<p>/</p>")}))

    result = run_cli("crawl", server.url("/"))

    assert [
        "--ignore-robots" in (warning["hint"] or "")
        for warning in result.json()["warnings"]
        if warning["code"] == "robots_unreachable"
    ] == [True]


# RFC 9309 2.2.1: a product token is letters, "_" and "-" only.
_NOT_TOKENS = ["Googlebot/2.1", "my bot", ""]
_TOKENS = ["Googlebot", "my-bot_x", DEFAULT_ROBOTS_TOKEN]


@pytest.mark.parametrize("token", _NOT_TOKENS)
def test_a_robots_user_agent_token_outside_rfc_9309_is_rejected(
    temp_workspace: TempWorkspace, token: str
) -> None:
    result = run_cli("crawl", "http://site.test/", "--robots-user-agent", token)

    assert (
        result.exit_code,
        [(error["code"], "--robots-user-agent" in error["message"]) for error in result.errors()],
    ) == (2, [("invalid_value", True)])


@pytest.mark.parametrize("token", _NOT_TOKENS)
def test_a_robots_user_agent_token_outside_rfc_9309_in_the_settings_file_is_refused(
    temp_workspace: TempWorkspace, token: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(
        f'[crawl]\nrobots_user_agent = "{token}"\n'.encode()
    )

    result = run_cli("crawl", "http://site.test/")

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"], "letters, '_' and '-'" in problem["message"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
    ) == (3, [("settings_invalid", "crawl.robots_user_agent", True)])


@pytest.mark.parametrize("token", _TOKENS)
def test_a_robots_user_agent_token_of_rfc_9309_is_taken(
    temp_workspace: TempWorkspace, fixture_site: StartSite, token: str
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>/</p>")}))

    result = run_cli("crawl", server.url("/"), "--robots-user-agent", token)

    config = json.loads(crawl_row(Path(result.json()["crawl_file"]))["config"])
    assert (result.exit_code, result.errors(), config["crawl"]["robots_user_agent"]) == (
        0,
        [],
        token,
    )


@pytest.mark.parametrize("token", _TOKENS)
def test_a_robots_user_agent_token_of_rfc_9309_in_the_settings_file_is_taken(
    temp_workspace: TempWorkspace, fixture_site: StartSite, token: str
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>/</p>")}))
    (temp_workspace.root / "openlinx.toml").write_bytes(
        f'[crawl]\nrobots_user_agent = "{token}"\n'.encode()
    )

    result = run_cli("crawl", server.url("/"))

    config = json.loads(crawl_row(Path(result.json()["crawl_file"]))["config"])
    assert (result.exit_code, result.errors(), config["crawl"]["robots_user_agent"]) == (
        0,
        [],
        token,
    )
