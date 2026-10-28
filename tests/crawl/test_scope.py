"""Scope decisions (020-add-crawl-core, crawling)."""

import json
import re
from typing import Any

import pytest

from spider.crawl.references import DiscoveredLink
from spider.crawl.scope import ScopeDecision, ScopeRules, apex_seed_named_by_page, scope_rules
from spider.crawl.urls import InvalidUrl, NormalizedUrl, normalize_url, parse_seed
from spider.store.records import LinkType


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


@pytest.mark.parametrize(
    ("url", "in_scope"),
    [
        ("http://site.test/blog/post", True),
        ("http://site.test/blog/", True),
        ("http://site.test/shop/", False),
        ("http://site.test/blogroll", False),
        ("http://www.site.test/blog/a", True),
    ],
)
def test_the_subfolder_scope_keeps_urls_inside_the_folder(url: str, in_scope: bool) -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/blog/"), scope="subfolder")

    assert rules.decide(NormalizedUrl(url)).in_scope is in_scope


def _link(link_type: LinkType, target: str) -> DiscoveredLink:
    return DiscoveredLink(
        type=link_type,
        target=NormalizedUrl(target),
        raw=target,
        element="a",
        attribute="href",
        rel=(),
        nofollow=False,
        skip_reason=None,
        declared_in="body",
        ordinal=1,
        is_internal=False,
    )


_TO_THE_APEX_MOSTLY: list[tuple[LinkType, str]] = [
    ("hyperlink", "http://site.test/a"),
    ("hyperlink", "http://site.test/b"),
    ("hyperlink", "http://www.site.test/c"),
]
_BLOG = (re.compile("/blog/"),)


@pytest.mark.parametrize(
    ("seed", "options", "links", "apex_seed"),
    [
        ("http://www.site.test/", {}, [("canonical", "http://site.test/")], "http://site.test/"),
        (
            "http://www.site.test:8080/blog/",
            {},
            [("canonical", "http://site.test:8080/blog/")],
            "http://site.test:8080/blog/",
        ),
        ("http://www.site.test/", {}, _TO_THE_APEX_MOSTLY, "http://site.test/"),
        (
            "http://www.site.test/",
            {},
            [("hyperlink", "http://site.test/a"), ("hyperlink", "http://www.site.test/c")],
            None,
        ),
        ("http://www.site.test/", {}, [("canonical", "http://www.site.test/")], None),
        # A canonical to the Seed's own host is the Page's word that www is the site.
        (
            "http://www.site.test/",
            {},
            [("canonical", "http://www.site.test/"), *_TO_THE_APEX_MOSTLY],
            None,
        ),
        ("http://www.site.test/", {}, [("misc", "http://site.test/feed")], None),
        ("http://site.test/", {}, [("canonical", "http://www.site.test/")], None),
        # www followed by a host that is no registrable domain: no apex to report.
        ("http://www.blog.site.test/", {}, [("canonical", "http://blog.site.test/")], None),
        ("http://www.127.0.0.1/", {}, [("canonical", "http://127.0.0.1/")], None),
        # The subdomains Scope crawls the apex already, so the Crawl misses nothing.
        (
            "http://www.site.test/",
            {"scope": "subdomains"},
            [("canonical", "http://site.test/")],
            None,
        ),
        ("http://www.site.test/", {"scope": "subdomains"}, _TO_THE_APEX_MOSTLY, None),
        # The hinted Seed is in the Scope, though the canonical's target is not.
        (
            "http://www.site.test/blog/",
            {"scope": "subdomains", "include": _BLOG},
            [("canonical", "http://site.test/")],
            None,
        ),
        (
            "http://www.site.test/blog/",
            {"scope": "subfolder"},
            [("canonical", "http://site.test/blog/")],
            "http://site.test/blog/",
        ),
    ],
)
def test_a_www_seed_is_reported_when_its_links_name_the_apex_outside_the_scope(
    seed: str, options: dict[str, Any], links: list[tuple[LinkType, str]], apex_seed: str | None
) -> None:
    rules = scope_rules(NormalizedUrl(seed), **options)

    found = apex_seed_named_by_page(
        NormalizedUrl(seed), [_link(link_type, target) for link_type, target in links], rules
    )

    assert found == apex_seed


_DECIDED = [
    NormalizedUrl(url)
    for url in (
        "http://site.test/",
        "https://www.site.test:8443/blog/a",
        "http://blog.site.test/blog/x",
        "http://other.test/blog/",
        "http://127.0.0.1:8080/blog/draft",
        "http://127.0.0.1:9000/",
        "http://localhost/blog/",
        "http://localhost:5000/x",
        "http://site.test/shop/draft",
    )
]


@pytest.mark.parametrize(
    ("seed", "options"),
    [
        ("http://site.test/", {}),
        ("http://www.site.test/", {}),
        ("http://www.site.test/", {"scope": "subdomains"}),
        # Hosts with no registrable domain: the record lists the Seed host itself.
        ("http://127.0.0.1:8080/", {"scope": "subdomains"}),
        ("http://localhost/", {"scope": "subdomains"}),
        ("http://site.test/blog/", {"scope": "subfolder"}),
        ("http://site.test/", {"include": _BLOG}),
        ("http://127.0.0.1:8080/", {"exclude": (re.compile("draft"),)}),
    ],
)
def test_the_recorded_scope_decides_as_the_scope_it_was_recorded_from(
    seed: str, options: dict[str, Any]
) -> None:
    rules = scope_rules(NormalizedUrl(seed), **options)

    rebuilt = ScopeRules.from_json(json.loads(json.dumps(rules.to_json())))

    assert [rebuilt.decide(url) for url in _DECIDED] == [rules.decide(url) for url in _DECIDED]


def test_the_subdomains_scope_records_the_registrable_domain_as_its_hosts() -> None:
    rules = scope_rules(NormalizedUrl("http://www.site.test/"), scope="subdomains")

    assert rules.to_json()["hosts"] == ["site.test"]
