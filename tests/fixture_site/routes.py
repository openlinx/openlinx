"""Sites declared as data: a `Site` maps paths to routes (design D9 of 000-scaffold-project)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Fixed, never `mimetypes`: on Windows that reads the registry and differs between machines.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".gz": "application/gzip",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, kw_only=True)
class RouteOptions:
    headers: Sequence[tuple[str, str]] = ()
    content_type: str | None = None


@dataclass(frozen=True)
class Page(RouteOptions):
    file: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class Status(RouteOptions):
    code: int


@dataclass(frozen=True)
class Redirect(RouteOptions):
    location: str
    status: int = 301


@dataclass(frozen=True)
class Robots(RouteOptions):
    text: str


@dataclass(frozen=True)
class Sitemap(RouteOptions):
    paths: Sequence[str]


@dataclass(frozen=True)
class SitemapIndex(RouteOptions):
    paths: Sequence[str]


Route = Page | Status | Redirect | Robots | Sitemap | SitemapIndex


def redirect_chain(prefix: str, hops: int, to: str) -> dict[str, Route]:
    """`<prefix>1` -> `<prefix>2` -> ... -> `<prefix><hops>` -> `to`."""
    targets = [f"{prefix}{n}" for n in range(2, hops + 1)] + [to]
    return {f"{prefix}{n}": Redirect(target) for n, target in enumerate(targets, start=1)}


@dataclass(frozen=True)
class Site:
    routes: dict[str, Route] = field(default_factory=dict)
    root: Path | None = None
