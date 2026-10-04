"""Pages, cursors and fields (design D6 of 010-add-workspace-and-cli-contract)."""

import base64
from typing import Any

import orjson

CURSOR_VERSION = 1


def encode_cursor(fingerprint: str, keyset: Any) -> str:
    payload = orjson.dumps({"v": CURSOR_VERSION, "q": fingerprint, "k": keyset})
    # Unpadded URL-safe base64 passes through a shell without quoting.
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str, fingerprint: str) -> Any:
    payload = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    return orjson.loads(payload)["k"]
