"""Share proxy URL normalization and basic shape checks across settings and recording."""

from urllib.parse import SplitResult, urlsplit


def proxy_url(value: str | None) -> str | None:
    """An empty input falls back to environment; a schemeless input names an HTTP proxy."""
    if not value:
        return None
    if "://" in value:
        return value
    return f"http://{value}"


def split_absolute_url(value: str) -> SplitResult | None:
    """Check for a scheme, a host and an in-range port without ASCII whitespace."""
    if any(ord(char) <= 32 for char in value):
        return None
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        return None
    return parts if parts.scheme and parts.hostname else None
