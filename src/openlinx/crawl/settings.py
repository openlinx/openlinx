"""Define the crawl settings table and its validation bounds."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openlinx.crawl.setting_rules import (
    as_auth,
    as_headers,
    as_rate,
    as_robots_token,
    as_timeout,
    as_user_agent,
    proxy_url,
)
from openlinx.naming import DEFAULT_ROBOTS_TOKEN
from openlinx.store.records import ScopeKind


class CrawlSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(
        5, ge=1, le=50, description="The most requests in flight to one host, 1 to 50."
    )
    check_external: bool = Field(
        True,
        description="Request each External URL once to record its response; false records it "
        "as skipped, unrequested.",
    )
    follow_nofollow: bool = Field(
        False,
        description="Follow nofollow hyperlinks, and every hyperlink of a Page whose robots "
        "directives say nofollow, like any other hyperlink.",
    )
    ignore_robots: bool = Field(
        False,
        description="Request URLs that robots.txt disallows; they are still recorded with "
        "blocked_by_robots_txt = 1.",
    )
    max_depth: int | None = Field(
        None,
        ge=0,
        description="The deepest Crawl Depth whose URLs are requested, the Seed's being 0; "
        "Resources of followed Pages are requested one deeper. No limit when unset.",
    )
    rate: float | None = Field(
        None,
        strict=True,
        description="The most requests per second that start to one host, robots.txt's "
        "included: a finite number above 0. No limit when unset.",
    )
    max_urls: int | None = Field(
        None,
        ge=1,
        description="The most URL requests the Crawl starts over its whole life, a continue's "
        "included; robots.txt requests do not count. No limit when unset.",
    )
    network_wait: int = Field(
        1800,
        ge=0,
        description="The seconds a Crawl paused by lost network access waits for its Seed to "
        "answer before it fails; 0 fails at once.",
    )
    user_agent: str | None = Field(
        None,
        description="The User-Agent request header of every request, robots.txt's included: "
        "visible ASCII characters, spaces and tabs only. The tool's name, version and project "
        "URL when unset.",
    )
    header: list[str] = Field(
        [],
        description="Custom Name: Value headers for Internal URLs and their robots.txt only; "
        "repeat entries to send several headers. Sensitive values are hidden in records.",
        json_schema_extra={"secret": "header"},
    )
    auth: str | None = Field(
        None,
        description="Preemptive Basic Auth user:password for Internal URLs and their robots.txt "
        "only; exact UTF-8 without trimming or normalization. Empty disables authentication.",
        json_schema_extra={"secret": "whole"},
    )
    proxy: str | None = Field(
        None,
        description="The HTTP proxy URL for every request, robots.txt's included; a nonempty "
        "value overrides proxy environment variables. A schemeless URL uses HTTP; empty uses "
        "the environment. Its password is hidden in records.",
        json_schema_extra={"secret": "url"},
    )
    timeout: float = Field(
        20,
        strict=True,
        description="Seconds within which a request attempt, its body included, must complete: "
        "a finite number above 0.",
    )
    retries: int = Field(
        2,
        ge=0,
        le=10,
        description="How many times, 0 to 10, a request that timed out, could not connect or "
        "got a 429 or 5xx status is tried again, after 1, 2, 4, ... seconds or as its "
        "Retry-After asks.",
    )
    max_redirects: int = Field(
        10,
        ge=0,
        le=50,
        description="The most consecutive redirects, 0 to 50, followed from the first URL of a "
        "Redirect Chain; the target of the next one is recorded as skipped.",
    )
    robots_user_agent: str = Field(
        DEFAULT_ROBOTS_TOKEN,
        description="The token that selects robots.txt groups and user-agent-prefixed "
        "X-Robots-Tag values, letters, '_' and '-' only; independent of the User-Agent "
        "request header.",
    )
    scope: ScopeKind = Field(
        "host",
        description="Which Internal URLs are in the Scope: host (the Seed hosts), subdomains "
        "(every host of their registrable domains) or subfolder (the Seed's folder).",
    )
    strip_params: list[str] = Field(
        [],
        description="Glob patterns of query parameter names, comma-separated, removed from the "
        "Seed and every discovered URL before it is recorded or requested.",
    )
    include: list[str] = Field(
        [],
        description="Regular expressions of Internal URLs in the Scope; when given, a URL that "
        "matches none is checked but not followed. Each is searched for in the normalised URL.",
    )
    exclude: list[str] = Field(
        [],
        description="Regular expressions of URLs that are never requested; each is searched "
        "for in the normalised URL.",
    )

    @field_validator("rate")
    @classmethod
    def _is_a_rate(cls, rate: float | None) -> float | None:
        return None if rate is None else as_rate(rate)

    @field_validator("timeout")
    @classmethod
    def _is_a_timeout(cls, timeout: float) -> float:
        return as_timeout(timeout)

    @field_validator("user_agent")
    @classmethod
    def _is_a_user_agent(cls, user_agent: str | None) -> str | None:
        return None if user_agent is None else as_user_agent(user_agent)

    @field_validator("auth")
    @classmethod
    def _is_auth(cls, auth: str | None) -> str | None:
        return None if auth is None or auth == "" else as_auth(auth)

    @field_validator("proxy")
    @classmethod
    def _is_a_proxy(cls, proxy: str | None) -> str | None:
        return proxy_url(proxy)

    @field_validator("robots_user_agent")
    @classmethod
    def _is_a_robots_token(cls, token: str) -> str:
        return as_robots_token(token)

    @field_validator("header")
    @classmethod
    def _are_headers(cls, headers: list[str]) -> list[str]:
        as_headers(headers)
        return headers
