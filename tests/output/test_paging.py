"""Cursors (design D6 of 010-add-workspace-and-cli-contract, cli-contract)."""

import re
from typing import Any

import pytest

from spider.output.paging import decode_cursor, encode_cursor

FINGERPRINT = "0123456789abcdef"
# Payloads of every length modulo 3, and bytes that plain base64 writes as + and /.
KEYSETS: list[Any] = [0, 12, 345, "ÿþ?>", [1, "a"], {"n": 99}]


@pytest.mark.parametrize("keyset", KEYSETS)
def test_cursor_round_trip(keyset: Any) -> None:
    assert decode_cursor(encode_cursor(FINGERPRINT, keyset), FINGERPRINT) == keyset


@pytest.mark.parametrize("keyset", KEYSETS)
def test_cursor_characters(keyset: Any) -> None:
    assert re.fullmatch(r"[A-Za-z0-9_-]+", encode_cursor(FINGERPRINT, keyset))
