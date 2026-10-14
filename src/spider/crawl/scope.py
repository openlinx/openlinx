"""Scope decisions: ScopeRules, built once from the Seed (020-add-crawl-core D4)."""

import re
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Literal

from spider.crawl.urls import NormalizedUrl, url_host, url_path
from spider.store.records import SkipReason

if TYPE_CHECKING:
    from publicsuffixlist import PublicSuffixList

# A plain alias, not a type statement: Typer reads it as the choices of --scope.
ScopeKind = Literal["host", "subdomains", "subfolder"]


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    is_internal: bool
    in_scope: bool
    skip_reason: SkipReason | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeRules:
    # In order: the Seed's host, then its www host, as the recorded Scope lists them.
    seed_hosts: tuple[str, ...]
    # Filled with --scope subdomains only: a host is internal when its registrable domain is one.
    registrable_domains: frozenset[str] = frozenset()
    folder: str | None = None
    include: tuple[re.Pattern[str], ...] = ()
    exclude: tuple[re.Pattern[str], ...] = ()

    @property
    def section_crawl(self) -> bool:
        return self.folder is not None

    def decide(self, url: NormalizedUrl) -> ScopeDecision:
        host = _without_trailing_dot(url_host(url))
        is_internal = host in self.seed_hosts or (
            bool(self.registrable_domains) and _registrable_domain(host) in self.registrable_domains
        )
        if any(pattern.search(url) for pattern in self.exclude):
            return ScopeDecision(is_internal=is_internal, in_scope=False, skip_reason="excluded")
        in_folder = self.folder is None or url_path(url).startswith(self.folder)
        included = not self.include or any(pattern.search(url) for pattern in self.include)
        return ScopeDecision(
            is_internal=is_internal, in_scope=is_internal and in_folder and included
        )


def scope_rules(
    seed: NormalizedUrl,
    *,
    scope: ScopeKind = "host",
    include: tuple[re.Pattern[str], ...] = (),
    exclude: tuple[re.Pattern[str], ...] = (),
) -> ScopeRules:
    host = _without_trailing_dot(url_host(seed))
    domain = _registrable_domain(host)
    # One way only: a www Seed never admits the apex, which the user did not name.
    www = (f"www.{host}",) if domain == host else ()
    path = url_path(seed)
    return ScopeRules(
        seed_hosts=(host, *www),
        registrable_domains=frozenset({domain})
        if scope == "subdomains" and domain
        else frozenset(),
        folder=path[: path.rfind("/") + 1] if scope == "subfolder" else None,
        include=include,
        exclude=exclude,
    )


# Hosts repeat across a Crawl, and the Public Suffix List lookup walks the host's labels.
@lru_cache(maxsize=1024)
def _registrable_domain(host: str) -> str | None:
    # The list would call "0.1" the registrable domain of 127.0.0.1, and a single label has none.
    bare = host.strip(".")
    if host.startswith("[") or "." not in bare or _is_ipv4(bare):
        return None
    return _public_suffixes().privatesuffix(host)


# The bundled list takes about 56 ms to parse; one copy serves the process.
@lru_cache(maxsize=1)
def _public_suffixes() -> "PublicSuffixList":
    from publicsuffixlist import PublicSuffixList  # off the startup path

    return PublicSuffixList()


def _without_trailing_dot(host: str) -> str:
    return host.removesuffix(".")


def _is_ipv4(host: str) -> bool:
    try:
        IPv4Address(host)
    except ValueError:
        return False
    return True
