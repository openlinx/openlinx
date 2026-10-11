"""Scope decisions (020-add-crawl-core, crawling)."""

import re

import pytest

from spider.crawl.scope import ScopeDecision, scope_rules
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


def test_the_apex_of_a_www_seed_is_external() -> None:
    rules = scope_rules(NormalizedUrl("http://www.site.test/"))

    assert rules.decide(NormalizedUrl("http://site.test/x")).is_internal is False


def test_subdomains_are_internal_with_the_subdomains_scope() -> None:
    rules = scope_rules(NormalizedUrl("http://www.site.test/"), scope="subdomains")

    assert rules.decide(NormalizedUrl("http://blog.site.test/")).is_internal is True


def test_a_public_suffix_is_not_treated_as_the_site() -> None:
    rules = scope_rules(NormalizedUrl("http://www.shop.co.uk/"), scope="subdomains")

    assert rules.decide(NormalizedUrl("http://other.co.uk/")).is_internal is False


def test_the_folder_of_a_seed_page_is_its_parent_folder() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/blog/post-1"), scope="subfolder")

    assert rules.folder == "/blog/"


def test_exclude_wins_over_include() -> None:
    rules = scope_rules(
        NormalizedUrl("http://site.test/blog/"),
        include=(re.compile("/blog/"),),
        exclude=(re.compile("draft"),),
    )

    assert rules.decide(NormalizedUrl("http://site.test/blog/draft-1")) == ScopeDecision(
        is_internal=True, in_scope=False, skip_reason="excluded"
    )


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


@pytest.mark.parametrize(
    ("seed", "url", "internal"),
    [
        ("www.site.test", "https://a.b.site.test/", True),
        ("site.test.", "https://blog.site.test/", True),
        ("site.test", "https://othersite.test/", False),
        ("www.amazonaws.com", "https://bucket.s3.amazonaws.com/", False),
        ("127.0.0.1", "http://127.0.0.2/", False),
        ("localhost", "http://other.localhost/", False),
    ],
)
def test_the_subdomains_scope_compares_registrable_domains(
    seed: str, url: str, internal: bool
) -> None:
    rules = scope_rules(_valid(parse_seed(seed)), scope="subdomains")

    assert rules.decide(_valid(normalize_url(url))).is_internal is internal


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://site.test/blog/a", ScopeDecision(is_internal=True, in_scope=True)),
        ("http://site.test/news/n", ScopeDecision(is_internal=True, in_scope=False)),
        ("http://other.test/blog/a", ScopeDecision(is_internal=False, in_scope=False)),
        (
            "http://other.test/logout",
            ScopeDecision(is_internal=False, in_scope=False, skip_reason="excluded"),
        ),
    ],
)
def test_include_and_exclude_patterns_decide_the_scope(url: str, expected: ScopeDecision) -> None:
    rules = scope_rules(
        NormalizedUrl("http://site.test/blog/"),
        include=(re.compile("/blog/"),),
        exclude=(re.compile("/logout$"),),
    )

    assert rules.decide(NormalizedUrl(url)) == expected
