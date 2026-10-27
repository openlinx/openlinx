"""The proxy variables (022-add-fetch-policy, fetching; seam 3)."""

import pytest

from spider.crawl.fetch.proxy import proxy_for, proxy_variables
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
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


# The variables as a process environment holds them, and the proxy of http://site.test/.
_PROXY_CASES = [
    ({"HTTP_PROXY": "http://upper:3128"}, "http://upper:3128"),
    ({"http_proxy": "http://lower:3128"}, "http://lower:3128"),
    ({"HTTP_PROXY": "http://upper:3128", "http_proxy": "http://lower:3128"}, "http://lower:3128"),
    ({"HTTPS_PROXY": "http://secure:3128"}, None),
    ({"ALL_PROXY": "http://every:3128"}, None),
    ({}, None),
]


@pytest.mark.parametrize(("environ", "proxy"), _PROXY_CASES)
def test_the_proxy_of_a_url(environ: dict[str, str], proxy: str | None) -> None:
    assert proxy_for("http://site.test/", proxy_variables(environ)) == proxy
