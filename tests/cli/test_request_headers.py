"""Guard header input refusal and selective argv recording through the CLI."""

import json
from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawls import crawl_row
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("joined", [False, True], ids=["split", "joined"])
@pytest.mark.parametrize(
    "header",
    [
        "NoColon",
        ": value",
        "Bad Name: value",
        "X-Env: staging\rInjected: value",
        "X-Env: staging\nInjected: value",
        "X-Env: staging\r\nInjected: value",
        "X-Env: staging\r",
        "X-Env: staging\n",
        "X-Env: staging\x00",
        "X-Env: staging\x7f",
        "X-Env: Мой бот",
    ],
)
def test_a_malformed_header_is_rejected(
    temp_workspace: TempWorkspace, fixture_site: StartSite, header: str, joined: bool
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))
    flags = [f"--header={header}"] if joined else ["--header", header]

    result = run_cli("crawl", server.url("/"), *flags)

    assert (result.exit_code, [error["code"] for error in result.errors()], server.requests) == (
        2,
        ["invalid_value"],
        (),
    )


def test_joined_header_arguments_hide_only_sensitive_values(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))

    result = run_cli(
        "crawl",
        server.url("/"),
        "--header=X-Env: staging",
        "--header",
        "Cookie: sid=abc123",
        "--header=cOoKiE: sid=def456",
        "--header",
        "X-Env: audit",
        "--header=Authorization: Bearer ghi789",
        "--header",
        "aUtHoRiZaTiOn: Bearer jkl012",
        "--header=Proxy-Authorization: Basic mno345",
        "--header",
        "X-Token: pqr678",
        "--header=X-Secret: stu901",
        "--header",
        "X-Api-Key: vwx234",
        "--header=X-Password: yz5678",
        "--header",
        "x-env: final: review=ready",
        "--retries=0",
    )

    assert result.exit_code == 0, result.stderr
    crawl_file = Path(result.json()["crawl_file"])
    row = crawl_row(crawl_file)
    assert json.loads(row["command_argv"]) == [
        "linx",
        "crawl",
        server.url("/"),
        "--header=X-Env: staging",
        "--header",
        "Cookie: ***",
        "--header=cOoKiE: ***",
        "--header",
        "X-Env: audit",
        "--header=Authorization: ***",
        "--header",
        "aUtHoRiZaTiOn: ***",
        "--header=Proxy-Authorization: ***",
        "--header",
        "X-Token: ***",
        "--header=X-Secret: ***",
        "--header",
        "X-Api-Key: ***",
        "--header=X-Password: ***",
        "--header",
        "x-env: final: review=ready",
        "--retries=0",
    ]
    assert json.loads(row["config"])["crawl"]["header"] == [
        "X-Env: staging",
        "Cookie: ***",
        "cOoKiE: ***",
        "X-Env: audit",
        "Authorization: ***",
        "aUtHoRiZaTiOn: ***",
        "Proxy-Authorization: ***",
        "X-Token: ***",
        "X-Secret: ***",
        "X-Api-Key: ***",
        "X-Password: ***",
        "x-env: final: review=ready",
    ]
