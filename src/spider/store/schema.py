"""The declared public schema, one metadata over the core tables and the Rule tables
(015-add-crawl-store D6; 018-add-schema-conventions D2, D3; 040-add-rules D14)."""

from spider.store.schema_core import (
    SCHEMA_VERSION,
    crawl,
    literal_values,
    metadata,
    origins,
    pages,
    public_table,
    public_tables,
    public_view,
    seeds,
    urls,
)
from spider.store.schema_rules import (
    affected_urls,
    analysed_pages,
    indexable_pages,
    internal_urls,
    issues,
    rules,
)

# Imported from here only: metadata holds the Rule tables once schema_rules has run.
__all__ = [
    "SCHEMA_VERSION",
    "affected_urls",
    "analysed_pages",
    "crawl",
    "indexable_pages",
    "internal_urls",
    "issues",
    "literal_values",
    "metadata",
    "origins",
    "pages",
    "public_table",
    "public_tables",
    "public_view",
    "rules",
    "seeds",
    "urls",
]
