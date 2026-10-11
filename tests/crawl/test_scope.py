"""Scope decisions (020-add-crawl-core, crawling)."""

from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl


def test_the_other_scheme_of_the_seed_host_is_internal() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/"))

    assert rules.decide(NormalizedUrl("https://site.test:8443/x")).is_internal is True


def test_another_host_is_external_by_default() -> None:
    rules = scope_rules(NormalizedUrl("http://site.test/"))

    assert rules.decide(NormalizedUrl("http://blog.site.test/")).is_internal is False
