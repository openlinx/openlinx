"""Verify the values Handlers receive and how their rows are written to the Store."""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.dialects import sqlite

from openlinx.crawl.engine.hooks import Hooks, UrlFailure, UrlResponse, UrlResult, handler
from openlinx.store.connections import connect
from openlinx.store.records import ErroredUrl, FetchedUrl, Provenance, SkippedUrl
from openlinx.store.types import Timestamp
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# By final state: the store record, and where the UrlResult keeps that outcome's values.
_OUTCOMES: dict[str, tuple[type, tuple[type, ...]]] = {
    "fetched": (FetchedUrl, (UrlResponse, UrlResult)),
    "skipped": (SkippedUrl, (UrlResult,)),
    "error": (ErroredUrl, (UrlFailure, UrlResult)),
}
# By final state, the urls columns that its record shares with the UrlResult.
_SHARED = {
    state: [
        name
        # The provenance its dispatch acted on is written back with each outcome.
        for name in [f.name for f in fields(record)] + [f.name for f in fields(Provenance)]
        if name not in {"url_id", "provenance"}
        and any(name in {f.name for f in fields(source)} for source in sources)
    ]
    for state, (record, sources) in _OUTCOMES.items()
}


def _value(result: UrlResult, name: str) -> object:
    for source in (result.response, result.failure, result):
        if source is not None and name in {f.name for f in fields(source)}:
            return getattr(source, name)
    raise AssertionError(f"no {name}")


@dataclass(frozen=True, slots=True)
class Values:
    url_id: int
    values: str


def _values(result: UrlResult) -> tuple[Values, ...]:
    shared = _SHARED.get(result.fetch_state, [])
    values = {name: _value(result, name) for name in shared}
    fetched_at = values.get("fetched_at")
    if isinstance(fetched_at, datetime):
        values["fetched_at"] = Timestamp().process_bind_param(fetched_at, sqlite.dialect())
    # As the store keeps a flag.
    stored = {name: int(v) if isinstance(v, bool) else v for name, v in values.items()}
    return (Values(result.url_id, json.dumps({"fetch_state": result.fetch_state, **stored})),)


def _write_values(connection: Connection, rows: Sequence[Values]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_values (url_id INTEGER, v TEXT)"))
    connection.execute(
        text("INSERT INTO test_values VALUES (:url_id, :v)"),
        [{"url_id": row.url_id, "v": row.values} for row in rows],
    )


def test_each_url_is_recorded_with_the_values_its_handlers_saw(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Robots("User-agent: *\nDisallow: /private\n"),
                # A link to a port nothing listens on: its robots.txt gets no response.
                "/": Page(
                    body='<a href="/a">A</a> <a href="/missing">Gone</a> '
                    '<a href="/logout">Out</a> <a href="/private">Private</a> '
                    '<a href="http://127.0.0.1:1/">Down</a> <a href="/broken">Broken</a> '
                    '<img src="/logo.png">'
                ),
                "/a": Page(body="<p>A</p>"),
                "/logo.png": Status(200),
                # The connection breaks inside the body: an error after its own request.
                "/broken": Page(body="x" * 100_000, reset_after=100),
            }
        )
    )
    hooks = Hooks()
    hooks = replace(hooks, handlers=(*hooks.handlers, handler("values", _values, _write_values)))

    crawl_file = crawl_result(server.url("/"), hooks, exclude=["/logout$"], retries=0).crawl_file

    expected_urls = sorted(
        [
            server.url("/"),
            server.url("/a"),
            server.url("/missing"),
            server.url("/logout"),
            server.url("/private"),
            "http://127.0.0.1:1/",
            server.url("/broken"),
            server.url("/logo.png"),
        ]
    )
    url_rows = _urls_rows(crawl_file)
    assert sorted(row["url"] for row in url_rows) == expected_urls
    recorded = {row["id"]: row for row in url_rows}

    seen = [(url_id, json.loads(v)) for url_id, v in query(crawl_file, "SELECT * FROM test_values")]
    assert sorted(recorded[url_id]["url"] for url_id, _ in seen) == expected_urls
    assert (
        sorted({values["fetch_state"] for _, values in seen}),
        [
            (url_id, name)
            for url_id, values in seen
            for name, value in values.items()
            if recorded[url_id][name] != value
        ],
    ) == (["error", "fetched", "skipped"], [])


def _urls_rows(file: Path) -> list[sqlite3.Row]:
    with closing(connect(file, read_only=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows: list[sqlite3.Row] = connection.execute("SELECT * FROM urls").fetchall()
        return rows


@dataclass(frozen=True, slots=True)
class Header:
    url_id: int
    name: str


def _headers(result: UrlResult) -> tuple[Header, ...]:
    headers = () if result.response is None else result.response.headers
    return tuple(Header(result.url_id, name) for name, _ in headers)


def _write_headers(connection: Connection, rows: Sequence[Header]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_headers (url_id INTEGER, name TEXT)"))
    connection.execute(
        text("INSERT INTO test_headers VALUES (:url_id, :name)"),
        [{"url_id": row.url_id, "name": row.name} for row in rows],
    )


def test_a_handler_s_rows_for_a_url_are_written_in_one_statement(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/a">A</a>'), "/a": Page(body="<p>A</p>")})
    )
    hooks = Hooks()
    hooks = replace(hooks, handlers=(*hooks.handlers, handler("headers", _headers, _write_headers)))
    inserts: list[str] = []

    def count(conn: object, cursor: object, statement: str, *args: object) -> None:
        if statement.startswith("INSERT INTO test_headers"):
            inserts.append(statement)

    event.listen(Engine, "before_cursor_execute", count)
    try:
        crawl_file = crawl_result(server.url("/"), hooks).crawl_file
    finally:
        event.remove(Engine, "before_cursor_execute", count)

    assert (len(inserts), query(crawl_file, "SELECT count(DISTINCT url_id) FROM test_headers")) == (
        2,
        [(2,)],
    )
    assert query(crawl_file, "SELECT count(*) > 2 FROM test_headers") == [(1,)]
