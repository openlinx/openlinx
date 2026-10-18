"""The rows of the Page data tables, loading no sqlalchemy (030-add-page-data D1, D16)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRow:
    url_id: int
    address: str
    url_encoded_address: str
    url_path: str
    url_query: str | None
    status_code: int
    last_modified: datetime | None
    crawl_timestamp: datetime
    # From the HTML: NULL for a Page that is not analysed or whose Page extractor failed (D2).
    title_1: str | None = None
    title_1_length: int | None = None
    title_2: str | None = None
    title_2_length: int | None = None
    title_count: int | None = None
    meta_description_1: str | None = None
    meta_description_1_length: int | None = None
    meta_description_2: str | None = None
    meta_description_2_length: int | None = None
    meta_description_count: int | None = None
    meta_keywords_1: str | None = None
    meta_keywords_1_length: int | None = None
    h1_1: str | None = None
    h1_1_length: int | None = None
    h1_2: str | None = None
    h1_2_length: int | None = None
    h1_count: int | None = None
    h2_1: str | None = None
    h2_1_length: int | None = None
    h2_2: str | None = None
    h2_2_length: int | None = None
    h2_count: int | None = None
