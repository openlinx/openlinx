"""The [crawl] settings table (020-add-crawl-core D11)."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from spider.naming import DEFAULT_ROBOTS_TOKEN, ROBOTS_USER_AGENT_PATTERN
from spider.store.records import ScopeKind


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
    max_urls: int | None = Field(
        None,
        ge=1,
        description="The most URL requests the Crawl starts; robots.txt requests do not "
        "count. No limit when unset.",
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

    @field_validator("robots_user_agent")
    @classmethod
    def _is_a_robots_token(cls, token: str) -> str:
        # The pattern the CLI checks too, with a message a person reads instead of the regex.
        if re.fullmatch(ROBOTS_USER_AGENT_PATTERN, token) is None:
            raise ValueError("a robots user-agent token has letters, '_' and '-' only (RFC 9309)")
        return token
