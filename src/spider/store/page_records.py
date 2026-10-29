"""The rows of the Page data tables, loading no sqlalchemy (030-add-page-data D1, D16)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from spider.store.records import DeclaredIn, LinkType

type SameSite = Literal["strict", "lax", "none"]
type Indexability = Literal["indexable", "non_indexable"]
type IndexabilityStatus = Literal[
    "blocked_by_robots_txt",
    "redirected",
    "client_error",
    "server_error",
    "noindex",
    "canonicalised",
]
# javascript_redirect is filled from v1.1, by JavaScript rendering.
type RedirectType = Literal["http_redirect", "http_refresh", "meta_refresh", "javascript_redirect"]
type LinkPosition = Literal["head", "navigation", "header", "footer", "sidebar", "content"]


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
    indexability: Indexability
    indexability_status: IndexabilityStatus | None
    response_time_ms: int
    last_modified: datetime | None
    redirect_url: str | None
    redirect_type: RedirectType | None
    set_cookie_count: int
    crawl_timestamp: datetime
    # The fields default to NULL, in column order. From the Page extractor: NULL for a Page that
    # is not analysed or whose Page extractor failed (D2): the titles, meta elements, headings,
    # meta_refresh, and the counts from word_count on.
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
    # From the URL's result, but meta_refresh: NULL only for a Page that is not analysed, and
    # the X-Robots-Tag fields are set for every Page.
    meta_robots: str | None = None
    meta_robots_noindex: bool | None = None
    meta_robots_nofollow: bool | None = None
    x_robots_tag: str | None = None
    x_robots_tag_noindex: bool | None = None
    x_robots_tag_nofollow: bool | None = None
    meta_refresh: str | None = None
    canonical_url: str | None = None
    canonical_link_element_1: str | None = None
    canonical_link_element_2: str | None = None
    http_canonical: str | None = None
    canonical_count: int | None = None
    canonical_relative: bool | None = None
    rel_next_1: str | None = None
    rel_prev_1: str | None = None
    http_rel_next_1: str | None = None
    http_rel_prev_1: str | None = None
    amphtml_link_element: str | None = None
    mobile_alternate_link: str | None = None
    word_count: int | None = None
    sentence_count: int | None = None
    average_words_per_sentence: float | None = None
    text_ratio_pct: float | None = None
    declared_language: str | None = None
    content_hash: str | None = None
    jsonld_item_count: int | None = None
    microdata_item_count: int | None = None
    jsonld_parse_error_count: int | None = None
    structured_data_types: tuple[str, ...] | None = None


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


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkRow:
    source_url_id: int
    ordinal: int
    # Stored as target_url_id: the writer finds the id in the unit that records the target URL.
    target: str
    type: LinkType
    declared_in: DeclaredIn
    element: str | None
    attribute: str | None
    anchor_text: str | None
    alt_text: str | None
    rel: str | None
    rel_nofollow: bool
    rel_ugc: bool
    rel_sponsored: bool
    hreflang: str | None
    media: str | None
    link_position: LinkPosition | None
