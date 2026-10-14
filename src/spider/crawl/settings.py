"""The [crawl] settings table (020-add-crawl-core D11)."""

from pydantic import BaseModel, ConfigDict, Field

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
    max_depth: int | None = Field(
        None,
        ge=0,
        description="The deepest Crawl Depth whose URLs are requested, the Seed's being 0; "
        "Resources of followed Pages are requested one deeper. No limit when unset.",
    )
    max_urls: int | None = Field(
        None,
        ge=1,
        description="The most URL requests over the Crawl's whole life, those of a continued "
        "Crawl included; robots.txt requests do not count. No limit when unset.",
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
