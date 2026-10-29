"""The proxy of each request, from the proxy variables (022-add-fetch-policy D1)."""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

# The keys of the environment table of crawl.config whose proxy URL may hold a password.
SECRET_KEYS = ("http_proxy", "https_proxy")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProxyVariables:
    """HTTP_PROXY, HTTPS_PROXY and NO_PROXY as a run read them; no other variable is honoured."""

    http: str | None = None
    https: str | None = None
    no_proxy: str | None = None

    @classmethod
    def of(cls, environ: Mapping[str, str]) -> "ProxyVariables":
        return cls(
            http=_proxy_url(_variable(environ, "http_proxy")),
            https=_proxy_url(_variable(environ, "https_proxy")),
            no_proxy=_variable(environ, "no_proxy"),
        )

    def for_url(self, url: str) -> str | None:
        """The proxy that a request for `url` goes through, None when it goes direct."""
        parts = urlsplit(url)
        proxy = {"http": self.http, "https": self.https}.get(parts.scheme)
        if proxy is None or _bypassed(parts.hostname or "", self.no_proxy or ""):
            return None
        return proxy

    def recorded(self) -> dict[str, str]:
        """The environment table of crawl.config: the variables that are set."""
        found = {"http_proxy": self.http, "https_proxy": self.https, "no_proxy": self.no_proxy}
        return {key: value for key, value in found.items() if value is not None}


def _variable(environ: Mapping[str, str], name: str) -> str | None:
    # The lower-case name first, as curl reads it. An empty value counts as unset. On Windows the
    # environment ignores letter case, so both names find the one variable.
    return environ.get(name) or environ.get(name.upper()) or None


def _proxy_url(value: str | None) -> str | None:
    # As curl does: a proxy given without a scheme is an http proxy, so HTTP_PROXY=proxy:3128
    # works instead of failing every request.
    if value is None or "://" in value:
        return value
    return f"http://{value}"


def _bypassed(host: str, no_proxy: str) -> bool:
    names = [name.strip().lower().removeprefix(".") for name in no_proxy.split(",")]
    return "*" in names or any(host == name or host.endswith(f".{name}") for name in names if name)
