"""A Crawl of the synthetic site checked by counts, every URL accounted for (026 D6)."""

from collections import Counter
from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from tests.fixture_site.synthetic.serve import Tally
from tests.fixture_site.synthetic.site import (
    EXTERNAL,
    FETCHED,
    OUTCOMES,
    PARSED,
    Pool,
    SyntheticSite,
    page_number,
    pool_index,
)

CLEAN = "clean"
MISSING_OUTCOME: Mapping[str, Any] = {
    **FETCHED,
    "status_code": 404,
    "parsed": 0,
    "parse_error": None,
}
# Checked, never parsed: an External URL is outside the Scope.
EXTERNAL_OUTCOME: Mapping[str, Any] = {
    **FETCHED,
    "status_code": 200,
    "parsed": 0,
    "parse_error": None,
}
_POOL_OUTCOMES = {"missing": MISSING_OUTCOME, "external": EXTERNAL_OUTCOME}
# Wrong rows named in the problems, at most.
EXAMPLES = 10


class UrlRow(NamedTuple):
    url: str
    fetch_state: str
    fetch_error: str | None
    status_code: int | None
    parsed: int
    parse_error: str | None


@dataclass(frozen=True, kw_only=True)
class Accounting:
    # By outcome kind, a fault's name or "clean": (Pages expected, recorded, as expected).
    pages: Mapping[str, tuple[int, int, int]]
    # By pool kind: (URLs expected, recorded).
    pools: Mapping[str, tuple[int, int]]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "pages": {
                kind: dict(zip(("expected", "recorded", "as_expected"), counts, strict=True))
                for kind, counts in self.pages.items()
            },
            "pools": {
                kind: dict(zip(("expected", "recorded"), counts, strict=True))
                for kind, counts in self.pools.items()
            },
            "problems": list(self.problems),
        }


def account(
    site: SyntheticSite,
    rows: Iterable[UrlRow],
    *,
    origin: str,
    recorded_pools: Set[str],
    tally: Tally | None = None,
) -> Accounting:
    """Checks each Page's row against its expected outcome, and the counts of every kind.

    `origin` is the site's own, the Seed's; External URLs are on the hosts of the External pool.
    `recorded_pools` names the pool kinds the build records ("resource", "not_followed",
    "missing", "external"); the others must have no row.
    """
    manifest = site.manifest()
    expected_pages = Counter({kind: count for kind, count in manifest["faults"].items() if count})
    expected_pages[CLEAN] = site.pages - sum(manifest["faults"].values())
    recorded: Counter[str] = Counter()
    as_expected: Counter[str] = Counter()
    pooled: Counter[str] = Counter()
    problems: list[str] = []
    wrong = unknown = 0
    for row in rows:
        parts = urlsplit(row.url)
        # A query makes another URL of the same path.
        path = parts.path if not parts.query else ""
        on_site = row.url.startswith(origin.rstrip("/") + "/")
        n = page_number(path, site.pages) if on_site else None
        found = pool_index(path) if n is None else None
        if found is not None and not _belongs(found[0], found[1], row.url, on_site=on_site):
            found = None
        if n is not None:
            fault = site.fault(n)
            kind = CLEAN if fault is None else fault.value
            expected = PARSED if fault is None else OUTCOMES[fault]
            recorded[kind] += 1
        elif found is not None:
            kind = found[0].kind
            pooled[kind] += 1
            if kind not in _POOL_OUTCOMES:
                continue
            expected = _POOL_OUTCOMES[kind]
        else:
            unknown += 1
            if unknown <= EXAMPLES:
                problems.append(f"{row.url} is no URL of the synthetic site")
            continue
        got = _outcome(row)
        if got == expected:
            as_expected[kind] += 1
        else:
            wrong += 1
            if wrong <= EXAMPLES:
                problems.append(f"{row.url} ({kind}) was recorded as {got}")
    pages = {
        kind: (expected_pages[kind], recorded[kind], as_expected[kind])
        for kind in sorted(expected_pages.keys() | recorded.keys())
    }
    for kind, (listed, counted, right) in pages.items():
        if not listed == counted == right:
            problems.append(
                f"{kind} Pages: {counted} of {listed} recorded, {right} with the expected outcome"
            )
    pools = {
        kind: (manifest["urls"][_URL_KEYS[kind]] if kind in recorded_pools else 0, pooled[kind])
        for kind in _URL_KEYS
    }
    for kind, (listed, counted) in pools.items():
        if listed != counted:
            problems.append(f"{kind} URLs: {counted} recorded, {listed} expected")
    if wrong > EXAMPLES:
        problems.append(f"{wrong - EXAMPLES} more URLs were recorded with another outcome")
    if unknown > EXAMPLES:
        problems.append(f"{unknown - EXAMPLES} more URLs are no URL of the synthetic site")
    if tally is not None:
        problems += _tally_problems(site, tally)
    return Accounting(pages=pages, pools=pools, problems=tuple(problems))


_URL_KEYS = {
    "resource": "resources",
    "not_followed": "not_followed",
    "missing": "missing",
    "external": "external",
}


def _belongs(pool: Pool, index: int, url: str, *, on_site: bool) -> bool:
    """An External URL is on the host its index names; every other pool is on the site."""
    if pool is EXTERNAL:
        return not on_site and url == pool.url(index)
    return on_site


def _outcome(row: UrlRow) -> dict[str, Any]:
    return {
        "fetch_state": row.fetch_state,
        "fetch_error": row.fetch_error,
        "status_code": row.status_code,
        "parsed": row.parsed,
        "parse_error": row.parse_error,
    }


def _tally_problems(site: SyntheticSite, tally: Tally) -> list[str]:
    problems = []
    if tally.pages_requested != site.pages:
        problems.append(f"the site served {tally.pages_requested} of {site.pages} Pages")
    if tally.pages_requested_more_than_once:
        problems.append(f"{tally.pages_requested_more_than_once} Pages were requested twice")
    return problems
