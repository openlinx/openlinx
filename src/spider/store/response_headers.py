"""The response_headers table's writer (022-add-fetch-policy D7)."""

from collections.abc import Sequence

from sqlalchemy import Connection, insert

from spider.store.records import ResponseHeaders
from spider.store.schema import response_headers

# A plain INSERT: a second row for a URL is a bug, which must fail as record_failed.
_INSERT = insert(response_headers)


def write_response_headers(connection: Connection, rows: Sequence[ResponseHeaders]) -> None:
    connection.execute(_INSERT, [{"url_id": row.url_id, "headers": row.headers} for row in rows])
