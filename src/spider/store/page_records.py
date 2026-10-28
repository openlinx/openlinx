"""The rows of the Page data tables, loading no sqlalchemy (030-add-page-data D1, D16)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type SameSite = Literal["strict", "lax", "none"]


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRow:
    url_id: int
    address: str
    url_encoded_address: str
    url_path: str
    url_query: str | None
    content_type: str
    status_code: int
    status: str | None
    response_time_ms: int
    last_modified: datetime | None
    set_cookie_count: int
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
    meta_robots: str | None = None
    meta_robots_noindex: bool | None = None
    meta_robots_nofollow: bool | None = None
    # From the response's headers, for every Page.
    x_robots_tag: str | None = None
    x_robots_tag_noindex: bool | None = None
    x_robots_tag_nofollow: bool | None = None
    word_count: int | None = None
    sentence_count: int | None = None
    average_words_per_sentence: float | None = None
    text_ratio_pct: float | None = None
    declared_language: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CookieRow:
    url_id: int
    ordinal: int
    name: str
    domain: str | None
    path: str | None
    expires: datetime | None
    max_age: int | None
    secure: bool
    http_only: bool
    partitioned: bool
    same_site: SameSite | None
