"""The proxy variables (022-add-fetch-policy, fetching; seam 3)."""

import pytest

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
