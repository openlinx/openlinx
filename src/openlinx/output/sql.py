"""Project a Store SQL result into the Command's JSON document."""

from math import isinf
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openlinx.store.sql import SqlResult


def _json_cell(value: int | float | str | bytes | None) -> object:
    if isinstance(value, bytes):
        return {"blob_bytes": len(value)}
    if isinstance(value, float) and isinf(value):
        return {"real": "Infinity" if value > 0 else "-Infinity"}
    return value


def sql_document(result: "SqlResult") -> dict[str, object]:
    return {
        "columns": list(result.columns),
        "rows": [[_json_cell(value) for value in row] for row in result.rows],
        "row_count": result.row_count,
        "truncated": result.truncated,
        "limit": result.limit,
    }
