"""Pages, cursors and fields (design D6 of 010-add-workspace-and-cli-contract)."""

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import orjson

from openlinx.output.codes import INVALID_CURSOR, INVALID_VALUE, UNKNOWN_FIELD
from openlinx.output.diagnostics import OpenLinxError

CURSOR_VERSION = 1
CURSOR_CHARACTERS = re.compile(r"[A-Za-z0-9_-]+")
ALL_FIELDS = "all"


@dataclass(frozen=True)
class Fields:
    available: tuple[str, ...]
    default: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"available": list(self.available), "default": list(self.default)}


@dataclass(frozen=True)
class Page:
    items: Sequence[Mapping[str, Any]]
    total: int
    next_cursor: str | None
    # Keys that the JSON result puts before total, such as a version of what is listed.
    header: Mapping[str, Any] = field(default_factory=dict)


def paginate(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    cursor: str | None,
    fingerprint: str,
    fields: Sequence[str],
) -> Page:
    # A static list never changes under the reader, so the keyset can be the next index.
    start = 0 if cursor is None else decode_cursor(cursor, fingerprint)
    # The fingerprint matched, so only a hand-made cursor gets here with another keyset.
    if type(start) is not int or start < 0:
        raise _invalid_cursor()
    end = start + limit
    # A limit of 0 asks only for the count, so there is no next page to point to.
    more = limit > 0 and end < len(items)
    next_cursor = encode_cursor(fingerprint, end) if more else None
    return Page(project(items[start:end], fields), len(items), next_cursor)


def fingerprint(command: str, selection: Mapping[str, Any]) -> str:
    # Only what selects or orders items: --limit, --fields and --format may change between pages.
    canonical = orjson.dumps([command, selection], option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(canonical).hexdigest()[:16]


def select_fields(requested: str | None, fields: Fields) -> tuple[str, ...]:
    if requested is None:
        return fields.default
    # Lenient where the meaning is plain, strict where it is not: an empty name is refused.
    names = tuple(dict.fromkeys(name.strip() for name in requested.split(",")))
    if names == (ALL_FIELDS,):
        return fields.available
    if "" in names:
        raise OpenLinxError(
            INVALID_VALUE,
            f"--fields {requested!r} has an empty field name.",
            hint="Separate field names with single commas, such as --fields n,sq.",
        )
    for name in names:
        if name not in fields.available:
            raise OpenLinxError(
                UNKNOWN_FIELD,
                f"This Command has no field {name}.",
                hint=f"Use --fields with any of: {', '.join(fields.available)}, or {ALL_FIELDS}.",
                details={"field": name, "available": list(fields.available)},
            )
    return names


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


def _invalid_cursor() -> OpenLinxError:
    return OpenLinxError(
        INVALID_CURSOR,
        "The cursor was not made by this request, or it was altered.",
        hint="Pass the next_cursor of the same request, or leave out --cursor to start again.",
    )
