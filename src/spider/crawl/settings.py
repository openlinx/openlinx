"""The [crawl] settings table (020-add-crawl-core D11)."""

from pydantic import BaseModel, ConfigDict, Field


class CrawlSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(5, description="The most requests in flight to one host.")
    exclude: list[str] = Field(
        [],
        description="Regular expressions of URLs that are never requested; each is searched "
        "for in the normalised URL.",
    )
