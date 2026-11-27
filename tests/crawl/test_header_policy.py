"""Preserve explicit header choices through HTTP dispatch and repeated Crawl continuation."""

import json
import sqlite3
from contextlib import closing, nullcontext
from functools import partial
from typing import Any

import pytest

from openlinx.clock import SystemClock
from openlinx.crawl.fetch.fetcher import aiohttp_fetcher
from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import (
    CrawlOverrides,
    CrawlRequest,
    continue_crawl,
    plan_crawl,
    start_crawl,
)
from openlinx.services.crawls import create_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.records import CrawlFile
from openlinx.workspace.tables import SettingsTables
from tests.fixture_site.hosts import StartHosts, StartNamedHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site
from tests.fixture_site.server import ServerHandle
from tests.support.cli import CliResult, run_cli
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import crawl_row, sha256_of
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace

_DEFAULT = "OpenLinx/0.1.0.dev0 (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)"


@pytest.mark.parametrize(
    ("workspace", "flags", "internal", "external", "custom"),
    [
        ({}, {}, _DEFAULT, _DEFAULT, False),
        ({}, {"header": ["User-Agent: Header/1"]}, "Header/1", _DEFAULT, True),
        ({"header": ["User-Agent: FileHeader/1"]}, {}, "FileHeader/1", _DEFAULT, True),
        ({"user_agent": "File/1"}, {}, "File/1", "File/1", False),
        ({}, {"user_agent": "Cli/1"}, "Cli/1", "Cli/1", False),
        (
            {"user_agent": "File/1", "header": ["User-Agent: FileHeader/1"]},
            {},
            "File/1",
            "File/1",
            False,
        ),
        (
            {"user_agent": "File/1"},
            {"header": ["uSeR-aGeNt: Header/1"]},
            "Header/1",
            "File/1",
            True,
        ),
        (
            {"header": ["User-Agent: FileHeader/1"]},
            {"user_agent": "Cli/1"},
            "Cli/1",
            "Cli/1",
            False,
        ),
        (
            {},
            {"header": ["User-Agent: Header/1"], "user_agent": "Cli/1"},
            "Cli/1",
            "Cli/1",
            False,
        ),
        (
            {"user_agent": "File/1", "header": ["User-Agent: FileHeader/1"]},
            {"header": ["User-Agent: Header/1"]},
            "Header/1",
            "File/1",
            True,
        ),
        (
            {},
            {"header": ["User-Agent: Header/1"], "user_agent": _DEFAULT},
            _DEFAULT,
            _DEFAULT,
            False,
        ),
    ],
)
def test_user_agent_sources_and_scopes_have_literal_outcomes(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    workspace: dict[str, Any],
    flags: dict[str, Any],
    internal: str,
    external: str,
    custom: bool,
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        "[crawl]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in workspace.items())
    )
    hosts = fixture_hosts(
        Site({"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site({"/page": Page(body="Other")}),
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver, **flags)

    assert result.summary.state == "completed"
    assert [r.headers.getall("User-Agent") for r in hosts.site.requests] == [[internal], [internal]]
    assert [r.headers.getall("User-Agent") for r in hosts.other.requests] == [
        [external],
        [external],
    ]
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["request_policy"] == {"custom_user_agent": custom}
    assert type(config["request_policy"]["custom_user_agent"]) is bool
    assert config["crawl"]["header"] == flags.get("header", workspace.get("header", []))
    assert config["crawl"]["user_agent"] == flags.get("user_agent", workspace.get("user_agent"))


@pytest.mark.parametrize(
    ("workspace_user_agent", "flags", "dedicated", "headers", "custom"),
    [
        ("File/1", {"header": ["User-Agent: Header/1"]}, "File/1", ["User-Agent: Header/1"], True),
        (
            "File/1",
            {"header": ["User-Agent: Header/1"], "user_agent": "File/1"},
            "File/1",
            ["User-Agent: Header/1"],
            False,
        ),
        (None, {}, None, [], False),
    ],
)
def test_the_initial_crawl_records_the_selected_user_agent_winner(
    temp_workspace: TempWorkspace,
    workspace_user_agent: str | None,
    flags: dict[str, Any],
    dedicated: str | None,
    headers: list[str],
    custom: bool,
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        "[crawl]\n"
        + (f'user_agent = "{workspace_user_agent}"\n' if workspace_user_agent is not None else "")
    )
    plan = plan_crawl(
        CrawlRequest(
            seed="http://site.test/",
            cwd=temp_workspace.root,
            home=temp_workspace.home,
            workspace=None,
            command_argv=["service-crawl"],
            flags={"crawl": flags},
            secret_flags={},
        )
    )

    with create_crawl(plan.new_crawl, SystemClock(), Collected()) as created:
        pass

    config = json.loads(crawl_row(created.path)["config"])
    assert config["request_policy"] == {"custom_user_agent": custom}
    assert type(config["request_policy"]["custom_user_agent"]) is bool
    assert config["crawl"]["user_agent"] == dedicated
    assert config["crawl"]["header"] == headers


@pytest.mark.parametrize("dedicated_first", [True, False])
def test_cli_order_does_not_change_the_dedicated_winner(
    temp_workspace: TempWorkspace, fixture_site: StartSite, dedicated_first: bool
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    dedicated = ["--user-agent", "Cli/1"]
    generic = ["--header", "User-Agent: Header/1"]
    flags = dedicated + generic if dedicated_first else generic + dedicated

    result = run_cli("crawl", server.url("/"), *flags)

    assert result.exit_code == 0
    assert [r.headers.getall("User-Agent") for r in server.requests] == [["Cli/1"], ["Cli/1"]]


def test_an_omitted_cli_user_agent_keeps_the_explicit_workspace_value(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "File/1"\n')

    result = run_cli("crawl", server.url("/"))

    assert result.exit_code == 0
    assert [r.headers.getall("User-Agent") for r in server.requests] == [["File/1"], ["File/1"]]


def test_cli_headers_replace_the_workspace_list(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        '[crawl]\nheader = ["User-Agent: FileHeader/1", "X-Env: file"]\n'
    )

    result = run_cli("crawl", server.url("/"), "--header", "X-Env: cli", "--header", "x-env: audit")

    assert result.exit_code == 0
    assert [
        (r.headers.getall("X-Env"), r.headers.getall("User-Agent")) for r in server.requests
    ] == [
        (["cli", "audit"], [_DEFAULT]),
        (["cli", "audit"], [_DEFAULT]),
    ]


@pytest.mark.parametrize(
    "headers",
    [
        ["User-Agent: One/1", "user-agent: Two/1"],
        ["User-Agent: One/1", "USER-AGENT: One/1"],
    ],
)
def test_duplicate_custom_user_agent_fields_are_refused(
    temp_workspace: TempWorkspace, fixture_site: StartSite, headers: list[str]
) -> None:
    result, server = _crawl_with_custom_user_agents(temp_workspace, fixture_site, "flags", headers)

    assert (result.exit_code, [e["code"] for e in result.errors()], server.requests) == (
        2,
        ["invalid_value"],
        (),
    )


@pytest.mark.parametrize(
    "headers",
    [
        ["User-Agent: One/1", "user-agent: Two/1"],
        ["User-Agent: One/1", "USER-AGENT: One/1"],
    ],
)
def test_duplicate_workspace_user_agent_fields_are_refused(
    temp_workspace: TempWorkspace, fixture_site: StartSite, headers: list[str]
) -> None:
    result, server = _crawl_with_custom_user_agents(
        temp_workspace, fixture_site, "settings", headers
    )

    assert (result.exit_code, [e["code"] for e in result.errors()], server.requests) == (
        3,
        ["settings_invalid"],
        (),
    )


@pytest.mark.parametrize("source", ["flags", "settings"])
@pytest.mark.parametrize("headers", [["User-Agent:"], ["User-Agent:   "]])
def test_empty_or_whitespace_custom_user_agents_are_refused_before_dispatch(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, headers: list[str]
) -> None:
    result, server = _crawl_with_custom_user_agents(temp_workspace, fixture_site, source, headers)

    assert (result.exit_code, [e["code"] for e in result.errors()], server.requests) == (
        (2 if source == "flags" else 3),
        ["invalid_value" if source == "flags" else "settings_invalid"],
        (),
    )


def _crawl_with_custom_user_agents(
    workspace: TempWorkspace, fixture_site: StartSite, source: str, headers: list[str]
) -> tuple[CliResult, ServerHandle]:
    server = fixture_site(Site({"/": Page(body="Home")}))
    flags = [part for header in headers for part in ("--header", header)]
    flags += ["--user-agent", "Dedicated/1"]
    if source == "settings":
        (workspace.root / SETTINGS_FILE_NAME).write_text(
            f'[crawl]\nheader = {json.dumps(headers)}\nuser_agent = "Dedicated/1"\n'
        )
        flags = []
    return run_cli("crawl", server.url("/"), *flags), server


def test_provisional_seed_identity_agrees_between_a_page_and_its_robots(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/", status=301)}),
            "site.test": Site(
                {
                    "/robots.txt": Redirect("http://other.test/robots.txt"),
                    "/": Page(
                        body='<a href="/next">Next</a><a href="http://en.site.test/">Other</a>'
                    ),
                    "/next": Page(body="Next"),
                }
            ),
            "other.test": Site({}),
            "en.site.test": Site({"/": Page(body="Checked")}),
        }
    )

    result = crawl_result(
        "http://www.site.test/", resolver=hosts.resolver, header=["X-Env: staging"]
    )

    assert result.summary.state == "completed"
    assert [(r.path, r.headers.get("X-Env")) for r in hosts.servers["site.test"].requests] == [
        ("/robots.txt", "staging"),
        ("/", "staging"),
        ("/next", "staging"),
    ]
    assert [(r.path, r.headers.get("X-Env")) for r in hosts.servers["other.test"].requests] == [
        ("/robots.txt", None),
    ]
    assert [(r.path, r.headers.get("X-Env")) for r in hosts.servers["en.site.test"].requests] == [
        ("/robots.txt", None),
        ("/", None),
    ]


@pytest.mark.parametrize("dedicated", [False, True])
def test_repeated_continues_preserve_the_non_secret_header_winner(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, dedicated: bool
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="/last">Last</a>'),
                "/last": Page(body='<a href="http://other.test/page">Other</a>'),
            }
        ),
        Site({"/page": Page(body="Other")}),
    )
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "File/1"\n')
    flags: dict[str, Any] = {"header": ["User-Agent: Header/1", "X-Env: staging", "x-env: audit"]}
    if dedicated:
        flags["user_agent"] = "File/1"
    request = CrawlRequest(
        seed="http://site.test/",
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["service-crawl"],
        flags={"crawl": {**flags, "max_urls": 1}},
        secret_flags={},
    )
    first = start_crawl(
        plan_crawl(request),
        SystemClock(),
        Collected(),
        default_hooks(),
        fetchers=partial(aiohttp_fetcher, resolver=hosts.resolver),
    )
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "Changed/1"\n')
    configs = [json.loads(crawl_row(first.crawl_file)["config"])]

    second = continued(first, CrawlOverrides(max_urls=2), resolver=hosts.resolver)
    configs.append(json.loads(crawl_row(second.crawl_file)["config"]))
    third = continued(second, CrawlOverrides(max_urls=None), resolver=hosts.resolver)
    configs.append(json.loads(crawl_row(third.crawl_file)["config"]))

    assert [r.summary.state for r in (first, second, third)] == ["stopped", "stopped", "completed"]
    expected = "File/1" if dedicated else "Header/1"
    assert [r.headers.getall("User-Agent") for r in hosts.site.requests] == [[expected]] * 6
    assert [r.headers.getall("X-Env") for r in hosts.site.requests] == [["staging", "audit"]] * 6
    assert [c["request_policy"] for c in configs] == [{"custom_user_agent": not dedicated}] * 3
    assert [c["crawl"]["header"] for c in configs] == [
        ["User-Agent: Header/1", "X-Env: staging", "x-env: audit"]
    ] * 3
    assert [c["crawl"]["user_agent"] for c in configs] == ["File/1"] * 3

    assert [r.headers.getall("User-Agent") for r in hosts.other.requests] == [
        ["File/1"],
        ["File/1"],
    ]
    assert [r.headers.get("X-Env") for r in hosts.other.requests] == [None, None]


def test_service_inputs_retain_their_winner_without_cli_argv_evidence(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="http://other.test/page">Other</a>'),
            }
        ),
        Site({"/page": Page(body="Other")}),
    )
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "File/1"\n')
    plan = plan_crawl(
        CrawlRequest(
            seed="http://site.test/",
            cwd=temp_workspace.root,
            home=temp_workspace.home,
            workspace=None,
            command_argv=["service-crawl"],
            flags={"crawl": {"header": ["User-Agent: Header/1"], "max_urls": 1}},
            secret_flags={},
        )
    )
    stopped = start_crawl(
        plan,
        SystemClock(),
        Collected(),
        default_hooks(),
        fetchers=partial(aiohttp_fetcher, resolver=hosts.resolver),
    )
    assert stopped.summary.state == "stopped"
    assert json.loads(crawl_row(stopped.crawl_file)["command_argv"]) == ["service-crawl"]

    result = continued(stopped, CrawlOverrides(max_urls=None), resolver=hosts.resolver)

    assert result.summary.state == "completed"
    assert [r.headers.getall("User-Agent") for r in hosts.site.requests[2:]] == [
        ["Header/1"],
        ["Header/1"],
    ]
    assert [r.headers.getall("User-Agent") for r in hosts.other.requests] == [
        ["File/1"],
        ["File/1"],
    ]
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["request_policy"] == {"custom_user_agent": True}
    assert config["crawl"]["user_agent"] == "File/1"
    assert config["crawl"]["header"] == ["User-Agent: Header/1"]


@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
@pytest.mark.parametrize(
    ("policy", "headers"),
    [
        (policy, [])
        for policy in [
            False,
            True,
            0,
            1,
            "missing",
            None,
            [],
            "false",
            {},
            {"custom_user_agent": 0},
            {"custom_user_agent": 1},
            {"custom_user_agent": "false"},
            {"custom_user_agent": None},
            {"custom_user_agent": True},
        ]
    ]
    + [
        ({"custom_user_agent": True}, ["User-Agent:"]),
        ({"custom_user_agent": True}, ["User-Agent: One/1", "USER-AGENT: Two/1"]),
    ],
)
def test_a_direct_continue_refuses_invalid_request_policy_metadata(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    policy: Any,
    headers: list[str],
    read_only: bool,
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]
    config = json.loads(crawl_row(stopped.crawl_file)["config"])
    if policy == "missing":
        config.pop("request_policy", None)
    else:
        config["request_policy"] = policy
    if headers:
        config["crawl"]["header"] = headers
    with closing(sqlite3.connect(stopped.crawl_file)) as connection:
        connection.execute("UPDATE crawl SET config = ?", (json.dumps(config),))
        connection.commit()
    # A read can create SQLite's WAL sidecars after the editing connection removed them.
    assert json.loads(crawl_row(stopped.crawl_file)["config"]) == config
    before = sha256_of(stopped.crawl_file)
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    reporter = Collected()

    with (
        read_only_file(stopped.crawl_file) if read_only else nullcontext(),
        pytest.raises(OpenLinxError) as caught,
    ):
        continue_crawl(
            CrawlFile(stopped.crawl_id, stopped.crawl_file),
            CrawlOverrides(max_urls=None),
            SystemClock(),
            reporter,
            default_hooks(),
        )

    assert (caught.value.code, caught.value.exit_code, dict(caught.value.diagnostic.details)) == (
        "crawl_file_invalid",
        6,
        {"file": str(stopped.crawl_file)},
    )
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


def test_request_policy_cannot_be_registered_as_a_settings_table() -> None:
    with pytest.raises(TypeError, match="request_policy"):
        SettingsTables().register("request_policy", "tests.support.example_app:ExampleSettings")
