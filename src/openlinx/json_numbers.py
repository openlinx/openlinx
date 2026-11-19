"""Encode JSON documents without narrowing integers to 64 bits."""

from typing import Any

import orjson


def encode_json(value: Any) -> bytes:
    try:
        return orjson.dumps(value)
    except TypeError as error:
        if str(error) != "Integer exceeds 64-bit range":
            raise
    # Keep the ordinary encoding and CLI startup path. msgspec uses Python's digit limit.
    from msgspec import json

    return json.encode(value)
