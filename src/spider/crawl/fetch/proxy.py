"""The proxy of each request, from the proxy variables (022-add-fetch-policy D1)."""

from collections.abc import Mapping
from urllib.parse import urlsplit

# HTTP_PROXY, HTTPS_PROXY and NO_PROXY only: ALL_PROXY and the other schemes' are not honoured.
_HONOURED = ("http", "https", "no")


def proxy_variables(environ: Mapping[str, str]) -> dict[str, str]:
    """The proxy variables of a process environment, by lower-case scheme, and `no` for
    NO_PROXY; of two letter cases, the lower-case variable wins, as curl's does."""
    found = {}
    for key in _HONOURED:
        # On Windows the environment ignores letter case, so both names find the one variable.
        value = environ.get(f"{key}_proxy") or environ.get(f"{key.upper()}_PROXY")
        if value:
            found[key] = value
    return found


def proxy_for(url: str, proxies: Mapping[str, str]) -> str | None:
    """The proxy that a request for `url` goes through, None when it goes direct."""
    return proxies.get(urlsplit(url).scheme)
