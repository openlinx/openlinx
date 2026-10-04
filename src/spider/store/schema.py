"""The declared public schema of a crawl file (design D6 of 015-add-crawl-store)."""

from sqlalchemy import Column, MetaData, Table, Text

metadata = MetaData()

crawl = Table(
    "crawl",
    metadata,
    Column("id", Text, primary_key=True, comment="The crawl id."),
    comment="The Crawl's metadata, in exactly one row.",
    info={"change": 15},
)
