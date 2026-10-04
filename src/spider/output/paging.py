"""Pages, cursors and fields (design D6 of 010-add-workspace-and-cli-contract)."""

import base64
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import orjson

from spider.output.diagnostics import UsageError

CURSOR_VERSION = 1
CURSOR_CHARACTERS = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Fields:
    available: tuple[str, ...]
    default: tuple[str, ...]


@dataclass(frozen=True)
class Page:
    items: Sequence[Mapping[str, Any]]
    total: int
    next_cursor: str | None


def paginate(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    cursor: str | None,
    fingerprint: str,
    fields: Sequence[str],
) -> Page:
    # A static list never changes under the reader, so the keyset can be the next index.
    start: int = 0 if cursor is None else decode_cursor(cursor, fingerprint)
    end = start + limit
    # A limit of 0 asks only for the count, so there is no next page to point to.
    more = limit > 0 and end < len(items)
    next_cursor = encode_cursor(fingerprint, end) if more else None
    return Page(project(items[start:end], fields), len(items), next_cursor)


def project(items: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> list[dict[str, Any]]:
    return [{name: item[name] for name in fields} for item in items]


def encode_cursor(fingerprint: str, keyset: Any) -> str:
    payload = orjson.dumps({"v": CURSOR_VERSION, "q": fingerprint, "k": keyset})
    # Unpadded URL-safe base64 passes through a shell without quoting.
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str, fingerprint: str) -> Any:
    # urlsafe_b64decode would silently drop characters outside the alphabet.
    if not CURSOR_CHARACTERS.fullmatch(cursor):
        raise _invalid_cursor()
    try:
        payload = orjson.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except ValueError as error:
        raise _invalid_cursor() from error
    if (
        not isinstance(payload, dict)
        or payload.get("v") != CURSOR_VERSION
        or payload.get("q") != fingerprint
        or "k" not in payload
    ):
        raise _invalid_cursor()
    return payload["k"]


def _invalid_cursor() -> UsageError:
    return UsageError(
        "invalid_cursor",
        "The cursor was not made by this request, or it was altered.",
        hint="Pass the next_cursor of the same request, or leave out --cursor to start again.",
    )
