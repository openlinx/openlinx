"""Sites declared as data: a `Site` maps paths to routes (design D9 of 000-scaffold-project)."""

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


@dataclass(frozen=True)
class Page:
    file: str | None = None
    body: str | None = None


Route = Page


@dataclass(frozen=True)
class Site:
    routes: dict[str, Route] = field(default_factory=dict)
    root: Path | None = None
