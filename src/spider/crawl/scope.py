"""Scope decisions: ScopeRules, built once from the Seed (020-add-crawl-core D4)."""

from dataclasses import dataclass

from spider.crawl.urls import NormalizedUrl, url_host


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    is_internal: bool
    in_scope: bool


@dataclass(frozen=True, slots=True)
class ScopeRules:
    seed_hosts: frozenset[str]

    def decide(self, url: NormalizedUrl) -> ScopeDecision:
        is_internal = url_host(url) in self.seed_hosts
        return ScopeDecision(is_internal=is_internal, in_scope=is_internal)


def scope_rules(seed: NormalizedUrl) -> ScopeRules:
    return ScopeRules(frozenset({url_host(seed)}))
