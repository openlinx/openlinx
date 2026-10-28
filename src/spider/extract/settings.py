"""The [content_area] settings table (030-add-page-data D13)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from selectolax.lexbor import SelectolaxError

from spider.crawl.pages.links import parse_html
from spider.extract.content import ContentArea


class ContentAreaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(
        list(ContentArea().include),
        description="CSS selectors of the Content Area's roots; when empty, the root is <body>.",
    )
    exclude: list[str] = Field(
        list(ContentArea().exclude),
        description="CSS selectors of the elements left out of the Content Area.",
    )

    @field_validator("include", "exclude")
    @classmethod
    def _are_selectors(cls, selectors: list[str]) -> list[str]:
        # Compiled here, so a bad one stops the Crawl before any request.
        parser = parse_html("")
        for selector in selectors:
            try:
                parser.css(selector)
            except SelectolaxError as error:
                raise ValueError(f"{selector!r} is not a CSS selector") from error
        return selectors

    def content_area(self) -> ContentArea:
        return ContentArea(include=tuple(self.include), exclude=tuple(self.exclude))
