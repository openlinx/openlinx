"""Progress event lines on stderr (design D3 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import orjson


def event_line(name: str, data: Mapping[str, Any], now: datetime) -> bytes:
    return orjson.dumps({"event": name, "ts": timestamp_text(now), "data": data}) + b"\n"


def timestamp_text(now: datetime) -> str:
    # Milliseconds and a Z: the shortest form that sorts as text and parses everywhere.
    utc = now.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"
