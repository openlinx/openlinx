"""The schema service behind `spider schema` (design D6 of 015-add-crawl-store)."""

from typing import Any

from spider.store.schema import metadata


def describe_schema() -> list[dict[str, Any]]:
    return [
        {"name": table.name, "kind": "table", "description": table.comment, "columns": []}
        for table in metadata.tables.values()
    ]
