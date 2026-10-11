"""Scope decisions (020-add-crawl-core, crawling)."""

import pytest

from spider.crawl.scope import scope_rules
from spider.crawl.urls import InvalidUrl, NormalizedUrl, normalize_url, parse_seed


def test_the_other_scheme_of_the_seed_host_is_internal() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/"))

    assert rules.decide(NormalizedUrl("https://site.test:8443/x")).is_internal is True


def test_another_host_is_external_by_default() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/"))

    assert rules.decide(NormalizedUrl("http://blog.site.test/")).is_internal is False


def test_the_www_host_of_an_apex_seed_is_internal() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/"))

    assert rules.decide(NormalizedUrl("https://www.site.test/x")).is_internal is True


def _valid(url: NormalizedUrl | InvalidUrl) -> NormalizedUrl:
    if isinstance(url, InvalidUrl):
        raise TypeError(f"not a valid URL: {url.reason}")
    return url


@pytest.mark.parametrize(
    ("seed", "url", "internal"),
    [
        ("site.test", "https://www.site.test/", True),
        ("www.site.test", "https://site.test/", False),
        ("site.test", "https://blog.site.test/", False),
        ("site.test", "https://www.www.site.test/", False),
        ("www.site.test", "https://www.site.test:8443/a", True),
        ("site.test", "http://www.site.test:8080/", True),
        ("bücher.test", "https://www.xn--bcher-kva.test/", True),
        ("xn--bcher-kva.test", "https://www.bücher.test/", True),
        ("xn--e1afmkfd.xn--p1ai", "https://www.xn--e1afmkfd.xn--p1ai/", True),
        ("shop.co.uk", "https://www.shop.co.uk/", True),
        ("co.uk", "https://www.co.uk/", False),
        ("user.github.io", "https://www.user.github.io/", True),
        ("github.io", "https://www.github.io/", False),
        ("127.0.0.1:8765", "http://127.0.0.1:9000/", True),
        ("127.0.0.1:8765", "http://www.127.0.0.1/", False),
        ("[::1]:8765", "http://[::1]/", True),
        ("localhost:8080", "http://localhost/", True),
        ("localhost:8080", "http://www.localhost/", False),
        ("SITE.TEST", "https://WWW.Site.Test/", True),
        ("site.test.", "https://site.test/", True),
        ("site.test", "https://www.site.test./", True),
        ("127.0.0.1", "http://127.1/", False),
    ],
)
def test_seed_hosts_decide_what_is_internal(seed: str, url: str, internal: bool) -> None:
    rules = scope_rules(_valid(parse_seed(seed)))

    assert rules.decide(_valid(normalize_url(url))).is_internal is internal
