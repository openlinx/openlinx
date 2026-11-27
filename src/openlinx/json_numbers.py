"""Preserve exact integers in JSON documents across Python's conversion limits."""

from typing import Any

import orjson


def encode_json(value: Any) -> bytes:
    try:
        return orjson.dumps(value)
    except TypeError as error:
        if str(error) != "Integer exceeds 64-bit range":
            raise
    # The fallback converts wide integers directly to decimal JSON numbers.
    from pydantic_core import to_json

    return to_json(value, inf_nan_mode="null")


def decode_json_object(data: str) -> dict[str, Any]:
    """Read a JSON object, preserving recorded integers under a lower Python digit limit."""
    from msgspec import ValidationError, json

    try:
        return json.decode(data, type=dict[str, Any])
    except ValidationError:
        from pydantic_core import from_json

        value = from_json(data, allow_inf_nan=False)
        if not isinstance(value, dict):
            raise
        return value
