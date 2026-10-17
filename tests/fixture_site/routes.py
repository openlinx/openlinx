"""Sites declared as data: a `Site` maps paths to routes (design D9 of 000-scaffold-project)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Fixed, never `mimetypes`: on Windows that reads the registry and differs between machines.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, kw_only=True)
class RouteOptions:
    headers: Sequence[tuple[str, str]] = ()
    content_type: str | None = None
    delay: float = 0.0
    hang: bool = False
    # Send the headers and this many bytes of the body, then reset the connection.
    reset_after: int | None = None


@dataclass(frozen=True)
class Page(RouteOptions):
    file: str | None = None
    body: str | None = None
    template: bool = False

    def __post_init__(self) -> None:
        if (self.file is None) == (self.body is None):
            raise ValueError("a Page takes exactly one of file= and body=")


@dataclass(frozen=True)
class Status(RouteOptions):
    code: int
    # Served as text/html, as an error page is; None answers with an empty body.
    body: str | None = None


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


@dataclass(frozen=True)
class LargeFile(RouteOptions):
    """`size` bytes of the pattern 0, 1, ..., 255, 0, 1, ..., streamed."""

    size: int


Route = Page | Status | Redirect | Robots | Sitemap | SitemapIndex | LargeFile


def redirect_chain(prefix: str, hops: int, to: str) -> dict[str, Route]:
    """`<prefix>1` -> `<prefix>2` -> ... -> `<prefix><hops>` -> `to`."""
    targets = [f"{prefix}{n}" for n in range(2, hops + 1)] + [to]
    return {f"{prefix}{n}": Redirect(target) for n, target in enumerate(targets, start=1)}


@dataclass(frozen=True)
class Site:
    routes: dict[str, Route] = field(default_factory=dict)
    root: Path | None = None

    def __post_init__(self) -> None:
        reads_files = any(isinstance(r, Page) and r.file is not None for r in self.routes.values())
        if reads_files and self.root is None:
            raise ValueError("a Site with Page(file=...) routes needs root=")
