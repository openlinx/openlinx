"""The one body reader: a response body read up to its cap (022-add-fetch-policy D1)."""

from collections.abc import AsyncIterable
from dataclasses import dataclass

BODY_LIMIT = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Body:
    data: bytes
    # Larger than the cap, so not read in full.
    truncated: bool


async def read_body(chunks: AsyncIterable[bytes], limit: int = BODY_LIMIT) -> Body:
    """The body that `chunks` stream, cut at `limit` bytes; reading stops at the cap."""
    parts: list[bytes] = []
    size = 0
    async for chunk in chunks:
        if size + len(chunk) > limit:
            parts.append(chunk[: limit - size])
            return Body(b"".join(parts), truncated=True)
        parts.append(chunk)
        size += len(chunk)
    return Body(b"".join(parts), truncated=False)
