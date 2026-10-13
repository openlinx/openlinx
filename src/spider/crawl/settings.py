"""The [crawl] settings table (020-add-crawl-core D11)."""

from pydantic import BaseModel, ConfigDict, Field


class CrawlSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(5, description="The most requests in flight to one host.")
