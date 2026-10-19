"""Pages, cursors and fields (design D6 of 010-add-workspace-and-cli-contract)."""

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import orjson

from spider.output.codes import INVALID_CURSOR, INVALID_VALUE, UNKNOWN_FIELD
from spider.output.diagnostics import SpiderError

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


@dataclass(frozen=True, slots=True)
class PageRequest[After]:
    """The paging flags of one list request, its cursor already checked: a reader reads up to
    read_limit items after `after`, and page() makes the Page of them."""

    fields: tuple[str, ...]
    limit: int
    fingerprint: str
    # Paged by index, the number of items before the page; by keyset, the keys of the previous
    # page's last item, or None on the first page.
    after: After
    keys: tuple[str, ...]

    @staticmethod
    def by_index(
        fields: tuple[str, ...], *, limit: int, cursor: str | None, fingerprint: str
    ) -> "PageRequest[int]":
        start = 0 if cursor is None else decode_cursor(cursor, fingerprint)
        # The fingerprint matched, so only a hand-made cursor gets here with another position.
        if type(start) is not int or start < 0:
            raise _invalid_cursor()
        return PageRequest(fields, limit, fingerprint, start, ())

    @staticmethod
    def by_keys(
        fields: tuple[str, ...],
        *,
        limit: int,
        cursor: str | None,
        fingerprint: str,
        keys: Mapping[str, type],
    ) -> "PageRequest[tuple[Any, ...] | None]":
        """Paged by the values of `keys`, in order, each of its type."""
        after = None if cursor is None else _keys(decode_cursor(cursor, fingerprint), keys)
        return PageRequest(fields, limit, fingerprint, after, tuple(keys))

    @property
    def read_limit(self) -> int:
        # One more than the page: whether it is found says whether a next page exists.
        return self.limit + 1

    def page(
        self,
        found: Sequence[Mapping[str, Any]],
        total: int,
        *,
        header: Mapping[str, Any] = MappingProxyType({}),
    ) -> Page:
        """The Page of the items read after `after`, of which `found` holds at least read_limit
        when that many exist."""
        items = found[: self.limit]
        # A limit of 0 asks only for the count, so there is no next page to point to.
        more = self.limit > 0 and len(found) > self.limit
        next_cursor = encode_cursor(self.fingerprint, self._next(items)) if more else None
        return Page(project(items, self.fields), total, next_cursor, header)

    def _next(self, items: Sequence[Mapping[str, Any]]) -> Any:
        if isinstance(self.after, int):
            return self.after + self.limit
        return [items[-1][key] for key in self.keys]


def paginate(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    cursor: str | None,
    fingerprint: str,
    fields: Sequence[str],
) -> Page:
    # A static list never changes under the reader, so it pages by index.
    request = PageRequest.by_index(
        tuple(fields), limit=limit, cursor=cursor, fingerprint=fingerprint
    )
    return request.page(items[request.after :], len(items))


def _keys(keyset: Any, keys: Mapping[str, type]) -> tuple[Any, ...]:
    # The fingerprint matched, so only a hand-made cursor gets here with other keys; the exact
    # type, since True is an int to isinstance.
    types = tuple(keys.values())
    if not (
        isinstance(keyset, list)
        and len(keyset) == len(types)
        and all(type(key) is expected for key, expected in zip(keyset, types, strict=True))
    ):
        raise _invalid_cursor()
    return tuple(keyset)


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
        raise SpiderError(
            INVALID_VALUE,
            f"--fields {requested!r} has an empty field name.",
            hint="Separate field names with single commas, such as --fields n,sq.",
        )
    for name in names:
        if name not in fields.available:
            raise SpiderError(
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


def _invalid_cursor() -> SpiderError:
    return SpiderError(
        INVALID_CURSOR,
        "The cursor was not made by this request, or it was altered.",
        hint="Pass the next_cursor of the same request, or leave out --cursor to start again.",
    )
