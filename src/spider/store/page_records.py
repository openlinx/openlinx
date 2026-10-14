"""The rows of the Page data tables, loading no sqlalchemy (030-add-page-data D1, D16)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRow:
    url_id: int
    address: str
    url_encoded_address: str
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
