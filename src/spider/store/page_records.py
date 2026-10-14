"""The rows of the Page data tables, loading no sqlalchemy (030-add-page-data D1, D16)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRow:
    url_id: int
    address: str
    url_encoded_address: str
