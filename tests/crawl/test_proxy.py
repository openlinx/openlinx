"""Verify explicit and environment proxies through HTTP requests and recorded settings."""

import json
import socket
from contextlib import nullcontext
from pathlib import Path

import pytest

from openlinx.crawl.fetch.proxy import ProxyVariables
from openlinx.output.diagnostics import OpenLinxError
from openlinx.services.crawling import CrawlOverrides
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import continued, crawl_result, crawled
from tests.support.crawls import query
from tests.support.permissions import read_only_file
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SHOP = Site({"/": Page(body='<title>Shop</title><a href="/shoes">Shoes</a>')})


@pytest.mark.parametrize("source", ["flag", "joined_flag", "workspace"])
@pytest.mark.parametrize("credentials", ["", "u:pw@"])
def test_requests_go_through_the_proxy(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    source: str,
    credentials: str,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    explicit = proxy.url.replace("http://", f"http://{credentials}")
    recorded = proxy.url.replace("http://", "http://u:***@") if credentials else proxy.url
    args = ["http://site.test/"]
    expected_argv = ["linx", "crawl", "http://site.test/"]
    if source == "workspace":
        (temp_workspace.root / "openlinx.toml").write_text(
            f'[crawl]\nproxy = "{explicit}"\n', encoding="utf-8"
        )
    elif source == "joined_flag":
        args.append(f"--proxy={explicit}")
        expected_argv.append(f"--proxy={recorded}")
    else:
        args.extend(("--proxy", explicit))
        expected_argv.extend(("--proxy", recorded))

    crawl_file = crawled(*args)

    assert proxy.requests == (
        "http://site.test/robots.txt",
        "http://site.test/",
        "http://site.test/shoes",
    )
    assert query(crawl_file, "SELECT url, status_code FROM urls ORDER BY id") == [
        ("http://site.test/", 200),
        ("http://site.test/shoes", 404),
    ]
    [(argv, config)] = query(crawl_file, "SELECT command_argv, config FROM crawl")
    assert (json.loads(argv), json.loads(config)["crawl"]["proxy"]) == (
        expected_argv,
        recorded,
    )


@pytest.mark.parametrize("source", ["flag", "workspace", "service"])
def test_an_explicit_schemeless_proxy_uses_http(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    source: str,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    explicit = proxy.url.removeprefix("http://")
    if source == "workspace":
        (temp_workspace.root / "openlinx.toml").write_text(
            f'[crawl]\nproxy = "{explicit}"\n', encoding="utf-8"
        )
        file = crawled("http://site.test/", "--network-wait", "0", "--retries", "0")
    else:
        (temp_workspace.root / "openlinx.toml").write_text(
            '[crawl]\nproxy = "http://127.0.0.1:1"\n', encoding="utf-8"
        )
        file = (
            crawled(
                "http://site.test/",
                "--proxy",
                explicit,
                "--network-wait",
                "0",
                "--retries",
                "0",
            )
            if source == "flag"
            else crawl_result(
                "http://site.test/", proxy=explicit, network_wait=0, retries=0
            ).crawl_file
        )

    assert proxy.requests == (
        "http://site.test/robots.txt",
        "http://site.test/",
        "http://site.test/shoes",
    )
    [(config,)] = query(file, "SELECT config FROM crawl")
    assert json.loads(config)["crawl"]["proxy"] == proxy.url


@pytest.mark.parametrize(
    ("source", "bypass"),
    [("flag", False), ("workspace", False), ("service", False), ("service", True)],
)
def test_an_empty_proxy_flag_restores_environment_handling(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    bypass: bool,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    workspace_proxy = fixture_proxy(hosts.resolver)
    environment_proxy = fixture_proxy(hosts.resolver)
    monkeypatch.setenv("HTTP_PROXY", environment_proxy.url)
    if bypass:
        monkeypatch.setenv("NO_PROXY", "site.test")
    explicit = "" if source == "workspace" else workspace_proxy.url
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[crawl]\nproxy = "{explicit}"\n', encoding="utf-8"
    )

    if source == "flag":
        file = crawled("http://site.test/", "--proxy", "")
    elif source == "workspace":
        file = crawled("http://site.test/")
    else:
        file = crawl_result("http://site.test/", proxy="", resolver=hosts.resolver).crawl_file

    assert workspace_proxy.requests == ()
    assert environment_proxy.requests == (
        ()
        if bypass
        else (
            "http://site.test/robots.txt",
            "http://site.test/",
            "http://site.test/shoes",
        )
    )
    assert [request.path for request in hosts.site.requests] == ["/robots.txt", "/", "/shoes"]
    [(config,)] = query(file, "SELECT config FROM crawl")
    assert json.loads(config)["crawl"]["proxy"] is None


@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
def test_continue_refuses_an_explicit_proxy_password_without_a_fresh_value(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    read_only: bool,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    stopped = crawl_result(
        "http://site.test/", proxy=proxy.url.replace("http://", "http://u:pw@"), max_urls=1
    )
    assert stopped.summary.state == "stopped"
    [(config,)] = query(stopped.crawl_file, "SELECT config FROM crawl")
    assert json.loads(config)["crawl"]["proxy"] == proxy.url.replace("http://", "http://u:***@")
    requests = proxy.requests
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}

    with (
        read_only_file(stopped.crawl_file) if read_only else nullcontext(),
        pytest.raises(OpenLinxError) as caught,
    ):
        continued(stopped, CrawlOverrides(max_urls=None))

    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)
    assert "crawl.proxy" in (caught.value.diagnostic.hint or "")
    assert "--proxy" in (caught.value.diagnostic.hint or "")
    assert proxy.requests == requests
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files


def test_the_http_proxy_variable_is_honoured(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The crawler resolves only the proxy's address: site.test is known to the proxy alone.
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    monkeypatch.setenv("HTTP_PROXY", proxy.url)

    crawled("http://site.test/")

    assert proxy.requests == (
        "http://site.test/robots.txt",
        "http://site.test/",
        "http://site.test/shoes",
    )


def test_a_lower_case_proxy_variable_is_honoured(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    monkeypatch.setenv("http_proxy", proxy.url)

    crawled("http://site.test/")

    assert "http://site.test/" in proxy.requests


def test_no_proxy_bypasses_the_proxy(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    monkeypatch.setenv("NO_PROXY", "site.test")

    # Direct: the crawler resolves site.test itself, through the DNS resolver hook.
    crawl_result("http://site.test/", resolver=hosts.resolver)

    assert (proxy.requests, [request.path for request in hosts.site.requests]) == (
        (),
        ["/robots.txt", "/", "/shoes"],
    )


def test_a_proxy_password_from_a_variable_is_redacted(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    with_password = proxy.url.replace("http://", "http://u:pw@")
    monkeypatch.setenv("HTTP_PROXY", with_password)
    # Proxy settings are secret even without a password, so the whole URL is recorded as ***.
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    monkeypatch.setenv("NO_PROXY", "intranet.local")

    [(config,)] = query(crawled("http://site.test/"), "SELECT config FROM crawl")

    assert json.loads(config)["environment"] == {
        "http_proxy": proxy.url.replace("http://", "http://u:***@"),
        "https_proxy": "***",
        "no_proxy": "intranet.local",
    }


def test_only_the_proxy_variables_that_are_set_are_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fixture_site(SHOP)
    [(without,)] = query(crawled(server.url("/")), "SELECT config FROM crawl")
    # Only a bypass list, as a laptop on a corporate network may keep set.
    monkeypatch.setenv("NO_PROXY", "intranet.local")
    [(bypass_only,)] = query(crawled(server.url("/")), "SELECT config FROM crawl")

    assert ("environment" in json.loads(without), json.loads(bypass_only)["environment"]) == (
        False,
        {"no_proxy": "intranet.local"},
    )


def test_a_continue_records_the_proxy_variables_it_fetches_through(
    temp_workspace: TempWorkspace, fixture_site: StartSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fixture_site(SHOP)
    monkeypatch.setenv("NO_PROXY", "intranet.local")
    stopped = crawl_result(server.url("/"), max_urls=1)
    # The laptop moved to another network: another bypass list, and an https proxy with a
    # password, which this http site does not go through.
    monkeypatch.setenv("NO_PROXY", "branch.local")
    monkeypatch.setenv("HTTPS_PROXY", "http://u:pw@proxy.corp:3128")

    continued(stopped, CrawlOverrides(max_urls=None))
    [(config,)] = query(stopped.crawl_file, "SELECT config FROM crawl")

    assert json.loads(config)["environment"] == {
        "https_proxy": "http://u:***@proxy.corp:3128",
        "no_proxy": "branch.local",
    }


# The variables as a process environment holds them, a URL, and the proxy it goes through.
_PROXY_CASES = [
    ({"HTTP_PROXY": "http://upper:3128"}, "http://site.test/", "http://upper:3128"),
    ({"http_proxy": "http://lower:3128"}, "http://site.test/", "http://lower:3128"),
    (
        {"HTTP_PROXY": "http://upper:3128", "http_proxy": "http://lower:3128"},
        "http://site.test/",
        "http://lower:3128",
    ),
    # An empty variable counts as unset, as curl reads it.
    (
        {"HTTP_PROXY": "http://upper:3128", "http_proxy": ""},
        "http://site.test/",
        "http://upper:3128",
    ),
    ({"HTTPS_PROXY": "http://secure:3128"}, "http://site.test/", None),
    (
        {"HTTP_PROXY": "http://upper:3128", "HTTPS_PROXY": "http://secure:3128"},
        "https://site.test/",
        "http://secure:3128",
    ),
    ({"ALL_PROXY": "http://every:3128"}, "http://site.test/", None),
    ({}, "http://site.test/", None),
    # A proxy without a scheme, as many corporate setups give it, is an http proxy.
    ({"HTTP_PROXY": "proxy.corp:3128"}, "http://site.test/", "http://proxy.corp:3128"),
    ({"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "site.test"}, "http://site.test/", None),
    ({"HTTPS_PROXY": "http://secure:3128", "NO_PROXY": "site.test"}, "https://site.test/", None),
    ({"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "SITE.TEST"}, "http://site.test/", None),
    (
        {"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "intranet.local, .test"},
        "http://site.test/",
        None,
    ),
    ({"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "test"}, "http://site.test/", None),
    ({"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "*"}, "http://site.test/", None),
    (
        {"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "www.site.test"},
        "http://site.test/",
        "http://upper:3128",
    ),
    (
        {"HTTP_PROXY": "http://upper:3128", "NO_PROXY": "ite.test"},
        "http://site.test/",
        "http://upper:3128",
    ),
]


@pytest.mark.parametrize(("environ", "url", "proxy"), _PROXY_CASES)
def test_the_proxy_of_a_url(environ: dict[str, str], url: str, proxy: str | None) -> None:
    assert ProxyVariables.of(environ).for_url(url) == proxy


def test_a_proxy_that_is_down_is_named_in_the_failure(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A port that nothing listens on: the proxy is down, not the site.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{port}")

    # The Seed gets no response, so the Crawl would pause at once: it fails instead.
    result = run_cli("crawl", "http://site.test/", "--retries", "0", "--network-wait", "0")
    [(fetch_error, message)] = query(
        Path(result.json()["crawl_file"]),
        "SELECT fetch_error, fetch_error_message FROM urls WHERE url = 'http://site.test/'",
    )

    assert (
        fetch_error,
        "ClientProxyConnectionError" in message,
        f"127.0.0.1:{port}" in message,
    ) == (
        "connection_refused",
        True,
        True,
    )
