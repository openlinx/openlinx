"""A seeded synthetic site of up to 500,000 Pages, computed per request (026-add-parse-pool D6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from tests.fixture_site.routes import Bytes, Route, Site

HTML = "text/html; charset=utf-8"


class Fault(StrEnum):
    NESTED_DIVS = "nested_divs"


NO_FAULTS: Mapping[Fault, float] = {}


def page_path(n: int) -> str:
    return "/" if n == 0 else f"/p/{n}"


def _page_number(path: str, pages: int) -> int | None:
    if path == "/":
        return 0
    digits = path.removeprefix("/p/")
    if digits == path or not digits.isdigit() or str(int(digits)) != digits:
        return None
    n = int(digits)
    return n if 0 < n < pages else None


@dataclass(frozen=True, kw_only=True)
class SyntheticSite:
    seed: int
    pages: int
    fanout: int = 50
    shares: Mapping[Fault, float] = field(default_factory=dict)

    def children(self, n: int) -> range:
        first = n * self.fanout + 1
        return range(min(first, self.pages), min(first + self.fanout, self.pages))

    def render(self, n: int) -> bytes:
        links = "".join(f'<a href="{page_path(child)}">{child}</a>' for child in self.children(n))
        return f"<!doctype html><html><body>{links}</body></html>".encode()

    def route(self, path: str) -> Route | None:
        n = _page_number(path, self.pages)
        if n is None:
            return None
        return Bytes(self.render(n), content_type=HTML)

    def as_site(self) -> Site:
        return Site(resolve=self.route)
