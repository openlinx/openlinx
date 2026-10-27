"""The proxy variables (022-add-fetch-policy, fetching; seam 3)."""

import json
import socket

import pytest

from spider.crawl.fetch.proxy import ProxyVariables
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SHOP = Site({"/": Page(body='<title>Shop</title><a href="/shoes">Shoes</a>')})


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
    # A proxy URL without a password is recorded as *** too, as 015 records a secret.
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    monkeypatch.setenv("NO_PROXY", "intranet.local")

    [(config,)] = query(crawled("http://site.test/"), "SELECT config FROM crawl")

    assert json.loads(config)["environment"] == {
        "http_proxy": proxy.url.replace("http://", "http://u:***@"),
        "https_proxy": "***",
        "no_proxy": "intranet.local",
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

    [(fetch_error, message)] = query(
        crawled("http://site.test/", "--retries", "0"),
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
