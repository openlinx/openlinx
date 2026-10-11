"""URL normalisation: NormalizedUrl, made only here (020-add-crawl-core D13)."""

from dataclasses import dataclass
from typing import NewType
from urllib.parse import SplitResult, urlsplit, urlunsplit

NormalizedUrl = NewType("NormalizedUrl", str)

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True, slots=True)
class InvalidUrl:
    reason: str


def normalize_url(text: str) -> NormalizedUrl | InvalidUrl:
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return InvalidUrl("malformed")
    if parts.scheme not in _DEFAULT_PORTS:
        return InvalidUrl("unsupported_scheme")
    if not parts.hostname:
        return InvalidUrl("missing_host")
    return NormalizedUrl(urlunsplit(_normalized_parts(parts, port)))


def _normalized_parts(parts: SplitResult, port: int | None) -> SplitResult:
    netloc = parts.hostname or ""
    if port is not None and port != _DEFAULT_PORTS[parts.scheme]:
        netloc = f"{netloc}:{port}"
    return parts._replace(netloc=netloc, fragment="")
