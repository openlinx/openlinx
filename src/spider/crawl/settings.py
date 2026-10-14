"""The [crawl] settings table (020-add-crawl-core D11)."""

from pydantic import BaseModel, ConfigDict, Field


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
    exclude: list[str] = Field(
        [],
        description="Regular expressions of URLs that are never requested; each is searched "
        "for in the normalised URL.",
    )
