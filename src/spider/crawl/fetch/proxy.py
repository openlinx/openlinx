"""The proxy of each request, from the proxy variables (022-add-fetch-policy D1)."""

from collections.abc import Mapping
from urllib.parse import urlsplit
from urllib.request import getproxies_environment

# HTTP_PROXY, HTTPS_PROXY and NO_PROXY only: ALL_PROXY and the other schemes' are not honoured.
_HONOURED = ("http", "https", "no")


def proxy_variables() -> dict[str, str]:
    """The proxy variables set when a run starts, by lower-case scheme, and `no` for NO_PROXY;
    of two letter cases, the lower-case variable wins."""
    found = getproxies_environment()
    return {key: found[key] for key in _HONOURED if key in found}


def proxy_for(url: str, proxies: Mapping[str, str]) -> str | None:
    """The proxy that a request for `url` goes through, None when it goes direct."""
    return proxies.get(urlsplit(url).scheme)
