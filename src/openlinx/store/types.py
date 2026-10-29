"""Column types shared by every table of the public schema (design D6 of 015-add-crawl-store)."""

from datetime import UTC, datetime
from typing import Any, ClassVar

import orjson
from sqlalchemy import Dialect, Integer, Text
from sqlalchemy.types import TypeDecorator


class Timestamp(TypeDecorator[datetime]):
    """UTC as `YYYY-MM-DDTHH:MM:SS.sssZ`, which sorts as text."""

    impl = Text
    cache_ok = True
    format: ClassVar[str] = "timestamp"

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Json(TypeDecorator[Any]):
    impl = Text
    cache_ok = True
    format: ClassVar[str] = "json"

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else orjson.dumps(value).decode()


class Flag(TypeDecorator[bool]):
    """A boolean as INTEGER 0 or 1; SQLAlchemy's Boolean would declare the type BOOLEAN."""

    impl = Integer
    cache_ok = True
    format: ClassVar[str] = "boolean"

    def process_bind_param(self, value: bool | None, dialect: Dialect) -> int | None:
        return None if value is None else int(value)
