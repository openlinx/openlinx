"""Cursors (design D6 of 010-add-workspace-and-cli-contract, cli-contract)."""

import base64
import re
from collections.abc import Mapping
from typing import Any

import pytest

from spider.output.diagnostics import SpiderError
from spider.output.paging import Page, PageRequest, decode_cursor, encode_cursor

FINGERPRINT = "0123456789abcdef"
# Payloads of every length modulo 3, and bytes that plain base64 writes as + and /.
KEYSETS: list[Any] = [0, 12, 345, "ÿþ?>", [1, "a"], {"n": 99}]


@pytest.mark.parametrize("keyset", KEYSETS)
def test_cursor_round_trip(keyset: Any) -> None:
    assert decode_cursor(encode_cursor(FINGERPRINT, keyset), FINGERPRINT) == keyset


@pytest.mark.parametrize("keyset", KEYSETS)
def test_cursor_characters(keyset: Any) -> None:
    assert re.fullmatch(r"[A-Za-z0-9_-]+", encode_cursor(FINGERPRINT, keyset))


def _base64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


@pytest.mark.parametrize(
    "cursor",
    [
        "abc",
        "",
        "abcd!",
        _base64(b"not json"),
        _base64(b'{"v":2,"q":"0123456789abcdef","k":1}'),
        _base64(b'{"v":1,"q":"0123456789abcdef"}'),
        _base64(b"[1]"),
        encode_cursor("fedcba9876543210", 1),
    ],
)
def test_undecodable_cursor(cursor: str) -> None:
    with pytest.raises(SpiderError) as raised:
        decode_cursor(cursor, FINGERPRINT)

    assert raised.value.code == "invalid_cursor"


@pytest.mark.parametrize("keyset", ["x", None, 1.5, -3, True])
def test_a_cursor_whose_position_is_not_an_index_is_undecodable(keyset: Any) -> None:
    cursor = encode_cursor(FINGERPRINT, keyset)

    # Refused when the request is made, before anything is read.
    with pytest.raises(SpiderError) as raised:
        PageRequest.by_index(("n",), limit=1, cursor=cursor, fingerprint=FINGERPRINT)

    assert raised.value.code == "invalid_cursor"


def by_keys(cursor: str | None, keys: Mapping[str, type], limit: int = 1) -> PageRequest[Any]:
    return PageRequest.by_keys(
        ("url",), limit=limit, cursor=cursor, fingerprint=FINGERPRINT, keys=keys
    )


@pytest.mark.parametrize(
    ("keyset", "keys"),
    [
        (5, {"url": str}),
        ([5], {"url": str}),
        (["a", "b"], {"url": str}),
        ([True], {"n": int}),
        ([1], {"n": int, "url": str}),
    ],
)
def test_a_keyset_cursor_whose_keyset_has_another_shape_is_refused(
    keyset: Any, keys: Mapping[str, type]
) -> None:
    # The fingerprint matches: only a hand-made cursor has another keyset.
    with pytest.raises(SpiderError) as raised:
        by_keys(encode_cursor(FINGERPRINT, keyset), keys)

    assert raised.value.code == "invalid_cursor"


def test_a_keyset_cursor_gives_its_keys() -> None:
    cursor = encode_cursor(FINGERPRINT, [3, "a"])

    assert by_keys(cursor, {"n": int, "url": str}).after == (3, "a")


def test_a_keyset_page_of_limit_0_has_only_the_total() -> None:
    found = [{"n": 1, "url": "a"}]

    assert by_keys(None, {"url": str}, limit=0).page(found, 7) == Page([], 7, None)


def test_an_exactly_full_last_keyset_page_has_no_next_cursor() -> None:
    found = [{"url": "a"}, {"url": "b"}]

    assert by_keys(None, {"url": str}, limit=2).page(found, 2) == Page(found, 2, None)
