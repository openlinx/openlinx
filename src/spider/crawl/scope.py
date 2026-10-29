"""Scope decisions: ScopeRules, built once from the Seed (020-add-crawl-core D4)."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Address
from typing import TYPE_CHECKING

from spider.crawl.urls import NormalizedUrl, url_host, url_path, without_www
from spider.store.records import RecordedScope, ScopeKind, SkipReason

if TYPE_CHECKING:
    from publicsuffixlist import PublicSuffixList

    from spider.crawl.references import DiscoveredLink


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    is_internal: bool
    in_scope: bool
    skip_reason: SkipReason | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeRules:
    # In order: the Seed's host, then its www host, as the recorded Scope lists them.
    seed_hosts: tuple[str, ...]
    mode: ScopeKind = "host"
    # Filled with --scope subdomains only: a host is internal when its registrable domain is one.
    registrable_domains: frozenset[str] = frozenset()
    folder: str | None = None
    include: tuple[re.Pattern[str], ...] = ()
    exclude: tuple[re.Pattern[str], ...] = ()

    @property
    def section_crawl(self) -> bool:
        # --exclude alone narrows a whole-site Crawl; it makes no Section Crawl.
        return self.folder is not None or bool(self.include)

    @classmethod
    def from_json(cls, recorded: RecordedScope) -> "ScopeRules":
        """The rules crawl.scope was recorded from, for the continue (design D1)."""
        hosts = recorded["hosts"]
        return cls(
            seed_hosts=tuple(hosts),
            mode=recorded["mode"],
            # The subdomains record lists registrable domains, or the Seed host when it has none.
            registrable_domains=frozenset(
                host for host in hosts if _registrable_domain(host) == host
            )
            if recorded["mode"] == "subdomains"
            else frozenset(),
            folder=recorded["folder"],
            include=tuple(re.compile(pattern) for pattern in recorded["include"]),
            exclude=tuple(re.compile(pattern) for pattern in recorded["exclude"]),
        )

    def to_json(self) -> RecordedScope:
        """As crawl.scope records it (design D18)."""
        return {
            "mode": self.mode,
            # An IP address or a single label has no registrable domain to list.
            "hosts": sorted(self.registrable_domains) or list(self.seed_hosts),
            "folder": self.folder,
            "include": [pattern.pattern for pattern in self.include],
            "exclude": [pattern.pattern for pattern in self.exclude],
        }

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
        mode=scope,
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


def apex_seed_named_by_page(
    seed: NormalizedUrl, links: Iterable["DiscoveredLink"], rules: ScopeRules
) -> NormalizedUrl | None:
    """The Seed on its apex host, when the Seed is www. plus a registrable domain, its Page names
    the apex by its first canonical to either host or by more hyperlinks than to the Seed's
    host, and the Scope leaves that Seed out (D4)."""
    host = _without_trailing_dot(url_host(seed))
    apex = host.removeprefix("www.")
    if apex == host or _registrable_domain(apex) != apex:
        return None
    apex_seed = without_www(seed)
    # The warning says the apex part of the site is outside the Crawl: not so when it is in.
    if not _names_apex(links, host, apex) or rules.decide(apex_seed).in_scope:
        return None
    return apex_seed


def _names_apex(links: Iterable["DiscoveredLink"], host: str, apex: str) -> bool:
    to_apex = to_seed_host = 0
    for link in links:
        target_host = _without_trailing_dot(url_host(link.target))
        # The first canonical to either host is the Page's own word on which one is the site.
        if link.type == "canonical" and target_host in (apex, host):
            return target_host == apex
        if link.type == "hyperlink":
            to_apex += target_host == apex
            to_seed_host += target_host == host
    return to_apex > to_seed_host
