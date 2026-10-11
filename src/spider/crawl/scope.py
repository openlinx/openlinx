"""Scope decisions: ScopeRules, built once from the Seed (020-add-crawl-core D4)."""

import re
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Literal

from spider.crawl.urls import NormalizedUrl, url_host
from spider.store.records import SkipReason

if TYPE_CHECKING:
    from publicsuffixlist import PublicSuffixList

type ScopeKind = Literal["host", "subdomains", "subfolder"]


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    is_internal: bool
    in_scope: bool
    skip_reason: SkipReason | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeRules:
    seed_hosts: frozenset[str]
    # Filled with --scope subdomains only: a host is internal when its registrable domain is one.
    registrable_domains: frozenset[str] = frozenset()
    folder: str | None = None
    include: tuple[re.Pattern[str], ...] = ()
    exclude: tuple[re.Pattern[str], ...] = ()

    def decide(self, url: NormalizedUrl) -> ScopeDecision:
        host = _without_trailing_dot(url_host(url))
        is_internal = host in self.seed_hosts or (
            bool(self.registrable_domains) and registrable_domain(host) in self.registrable_domains
        )
        if any(pattern.search(url) for pattern in self.exclude):
            return ScopeDecision(is_internal=is_internal, in_scope=False, skip_reason="excluded")
        included = not self.include or any(pattern.search(url) for pattern in self.include)
        return ScopeDecision(is_internal=is_internal, in_scope=is_internal and included)


def scope_rules(
    seed: NormalizedUrl,
    *,
    scope: ScopeKind = "host",
    include: tuple[re.Pattern[str], ...] = (),
    exclude: tuple[re.Pattern[str], ...] = (),
) -> ScopeRules:
    host = _without_trailing_dot(url_host(seed))
    domain = registrable_domain(host)
    # One way only: a www Seed never admits the apex, which the user did not name.
    www = {f"www.{host}"} if domain == host else set()
    domains = frozenset({domain}) if scope == "subdomains" and domain else frozenset()
    folder = _folder(seed) if scope == "subfolder" else None
    return ScopeRules(
        seed_hosts=frozenset({host} | www),
        registrable_domains=domains,
        folder=folder,
        include=include,
        exclude=exclude,
    )


# Hosts repeat across a Crawl, and the Public Suffix List lookup walks the host's labels.
@lru_cache(maxsize=1024)
def registrable_domain(host: str) -> str | None:
    """The host's registrable domain, or None for an IP address or a single-label host."""
    if host.startswith("[") or "." not in host.strip(".") or _is_ipv4(host):
        return None
    return _public_suffixes().privatesuffix(host)


# The bundled list takes about 56 ms to parse; one copy serves the process.
@lru_cache(maxsize=1)
def _public_suffixes() -> "PublicSuffixList":
    from publicsuffixlist import PublicSuffixList  # off the startup path

    return PublicSuffixList()


def _folder(url: NormalizedUrl) -> str:
    path = "/" + url.split("/", 3)[3].partition("?")[0]
    return path[: path.rfind("/") + 1]


def _without_trailing_dot(host: str) -> str:
    return host.removesuffix(".")


def _is_ipv4(host: str) -> bool:
    try:
        IPv4Address(host)
    except ValueError:
        return False
    return True
