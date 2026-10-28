"""The hooks of a Crawl: handlers, passes and extractors (020-add-crawl-core D9; seam 2)."""

import json
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.dialects import sqlite

from spider.clock import Clock
from spider.crawl.engine.hooks import (
    Hooks,
    Pass,
    PassContext,
    UrlFailure,
    UrlResponse,
    UrlResult,
    handler,
)
from spider.crawl.pages.preparation import Extractor, PageInput, extractor
from spider.output.reporter import Collected
from spider.services.crawling import CrawlResult
from spider.services.hooks import default_hooks
from spider.store.connections import connect
from spider.store.crawls import crawl_summary
from spider.store.records import CrawlState, ErroredUrl, FetchedUrl, Provenance, SkippedUrl
from spider.store.types import Timestamp
from spider.store.writer import CrawlWriterReplayError
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.network import closed_port
from tests.support.sites import LATE_SHORTER_PATH, NINE_PAGES
from tests.support.sqlite_faults import disk_full_after
from tests.support.workspace import TempWorkspace


@dataclass(frozen=True, slots=True)
class Seen:
    url_id: int
    fetch_state: str


def _seen(result: UrlResult) -> tuple[Seen, ...]:
    return (Seen(result.url_id, result.fetch_state),)


def _write_seen(connection: Connection, rows: Sequence[Seen]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_seen (url_id INTEGER, state TEXT)"))
    connection.execute(
        text("INSERT INTO test_seen VALUES (:url_id, :state)"),
        [{"url_id": row.url_id, "state": row.fetch_state} for row in rows],
    )


def test_a_registered_handler_sees_each_recorded_outcome_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<a href="/a">A</a> <a href="/missing">Gone</a> '
                    '<a href="/logout">Out</a> <a href="/a">A again</a>'
                ),
                "/a": Page(body='<a href="/logout">Out</a>'),
                "/logout": Page(body="<p>Bye</p>"),
            }
        )
    )
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("seen", _seen, _write_seen)),
    )

    result = crawl_result(server.url("/"), hooks, exclude=["/logout$"])

    assert sorted(
        query(
            result.crawl_file,
            "SELECT urls.url, test_seen.state FROM test_seen "
            "JOIN urls ON urls.id = test_seen.url_id",
        )
    ) == [
        (server.url("/"), "fetched"),
        (server.url("/a"), "fetched"),
        (server.url("/logout"), "skipped"),
        (server.url("/missing"), "fetched"),
    ]


@pytest.mark.slow
def test_a_url_skipped_beyond_the_depth_limit_reaches_its_handlers_once_requeued(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LATE_SHORTER_PATH)
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("seen", _seen, _write_seen)),
    )

    result = crawl_result(server.url("/"), hooks, max_depth=2)

    assert query(
        result.crawl_file,
        "SELECT test_seen.state FROM test_seen JOIN urls ON urls.id = test_seen.url_id "
        "WHERE urls.url = ?",
        [server.url("/c")],
    ) == [("fetched",)]


def test_post_crawl_passes_run_before_a_crawl_is_completed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    seen: list[CrawlState] = []

    async def record_state(context: PassContext) -> None:
        seen.append((await context.writer.run_async(crawl_summary())).state)

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("state", record_state)))

    crawl_result(server.url("/"), hooks)

    assert seen == ["running"]


def test_post_crawl_passes_run_in_the_order_the_hooks_declare(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    ran: list[str] = []

    async def first(context: PassContext) -> None:
        ran.append("first")

    async def second(context: PassContext) -> None:
        ran.append("second")

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("first", first), Pass("second", second)))

    crawl_result(server.url("/"), hooks)

    assert ran == ["first", "second"]


def test_a_post_crawl_pass_gets_the_clock_of_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>")})
    clocks: list[Clock] = []

    async def record_the_clock(context: PassContext) -> None:
        clocks.append(context.clock)

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("clock", record_the_clock)))

    crawl_result("http://site.test/", hooks, clock=clock, fetcher=fetcher)

    assert clocks == [clock]


def test_post_crawl_passes_run_when_the_url_limit_stops_a_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    runs: list[str] = []

    async def count_runs(context: PassContext) -> None:
        runs.append("run")

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("count", count_runs)))

    crawl_result(server.url("/"), hooks, max_urls=3)

    assert runs == ["run"]


_RULES = ("missing_title", "missing_description", "missing_h1", "thin_content")


async def _materialise_issues(context: PassContext) -> None:
    """Writes an Issue of each rule for every URL, as 040's pass does."""

    def unit(connection: Connection) -> None:
        connection.execute(
            text("CREATE TABLE test_issues (url_id INTEGER, rule TEXT, details TEXT)")
        )
        urls = connection.execute(text("SELECT id, url FROM urls")).all()
        connection.execute(
            text("INSERT INTO test_issues VALUES (:url_id, :rule, :details)"),
            [
                {"url_id": id, "rule": rule, "details": json.dumps({"url": url, "why": rule * 40})}
                for id, url in urls
                for rule in _RULES
            ],
        )

    await context.writer.run_async(unit)


def test_a_full_disk_in_a_post_crawl_pass_fails_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_articles(120))
    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("issues", _materialise_issues)))

    with disk_full_after(pages=24):
        result = crawl_result(server.url("/"), hooks)

    assert (*_end_of(result), crawl_row(result.crawl_file)["state"]) == (
        "failed",
        "write_failed",
        "failed",
    )


def test_post_crawl_passes_do_not_run_for_a_failed_crawl(temp_workspace: TempWorkspace) -> None:
    runs: list[str] = []

    async def count_runs(context: PassContext) -> None:
        runs.append("run")

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("count", count_runs)))

    result = crawl_result(f"http://127.0.0.1:{closed_port()}/", hooks, network_wait=0)

    assert (result.summary.state, runs) == ("failed", [])


class Found(msgspec.Struct, frozen=True):
    url: str


def _exploding(tree: LexborHTMLParser, page: PageInput, config: None) -> Found:
    if page.url.endswith("/boom"):
        raise ValueError(page.url)
    return Found(page.url)


def _found(tree: LexborHTMLParser, page: PageInput, config: None) -> Found:
    return Found(page.url)


BOOM_SITE = Site(
    routes={
        "/": Page(body='<a href="/boom">Boom</a> <a href="/ok">OK</a>'),
        "/boom": Page(body='<a href="/deeper">Deeper</a>'),
        "/ok": Page(body="<p>OK</p>"),
        "/deeper": Page(body="<p>Deeper</p>"),
    }
)


def _with_extractors(*extractors: Extractor[Any, Any]) -> Hooks:
    hooks = default_hooks()
    return replace(hooks, extractors=(*hooks.extractors, *extractors))


def test_an_extractor_error_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("exploding", _exploding, None))
    )
    ((parsed, parse_error, message),) = query(
        result.crawl_file,
        "SELECT parsed, parse_error, parse_error_message FROM urls WHERE url = ?",
        [server.url("/boom")],
    )

    assert (parsed, parse_error, "exploding" in message) == (1, "extractor_error", True)


def test_the_crawl_continues_after_an_extractor_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("exploding", _exploding, None))
    )

    assert query(
        result.crawl_file, "SELECT parsed FROM urls WHERE url = ?", [server.url("/ok")]
    ) == [(1,)]


def test_links_of_a_page_whose_extractor_failed_are_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("exploding", _exploding, None))
    )

    assert query(
        result.crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", [server.url("/deeper")]
    ) == [("fetched",)]


@dataclass(frozen=True, slots=True)
class Outputs:
    url_id: int
    names: str


_EXPLODING = extractor("exploding", _exploding, None)
_FOUND = extractor("found", _found, None)


def _outputs(result: UrlResult) -> tuple[Outputs, ...]:
    found = [
        registered.name
        for registered in (_EXPLODING, _FOUND)
        if registered.output(result.outputs) is not None
    ]
    return (Outputs(result.url_id, ",".join(found)),)


def _write_outputs(connection: Connection, rows: Sequence[Outputs]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_outputs (url_id INTEGER, names TEXT)"))
    connection.execute(
        text("INSERT INTO test_outputs VALUES (:url_id, :names)"),
        [{"url_id": row.url_id, "names": row.names} for row in rows],
    )


def test_handlers_get_the_outputs_of_the_extractors_that_did_not_fail(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = _with_extractors(_EXPLODING, _FOUND)
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("outputs", _outputs, _write_outputs)),
    )

    result = crawl_result(server.url("/"), hooks)

    assert query(
        result.crawl_file,
        "SELECT urls.url, test_outputs.names FROM test_outputs "
        "JOIN urls ON urls.id = test_outputs.url_id WHERE urls.url IN (?, ?) ORDER BY urls.id",
        [server.url("/boom"), server.url("/ok")],
    ) == [(server.url("/boom"), "found"), (server.url("/ok"), "exploding,found")]


def test_parse_failures_are_counted_in_one_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/boom">1</a> <a href="/2/boom">2</a>'),
                "/boom": Page(body="<p>1</p>"),
                "/2/boom": Page(body="<p>2</p>"),
            }
        )
    )

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("exploding", _exploding, None))
    )

    assert [
        (warning["code"], warning["details"]["count"]) for warning in result.to_json()["warnings"]
    ] == [("parse_failed", 2)]


def _boom(result: UrlResult) -> tuple[Seen, ...]:
    if result.url.endswith("/boom"):
        raise ValueError(result.url)
    return (Seen(result.url_id, result.fetch_state),)


def _boom_too(result: UrlResult) -> tuple[Outputs, ...]:
    if result.url.endswith("/boom"):
        raise KeyError("canonical")
    return ()


def test_two_handlers_that_fail_on_one_url_count_it_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/boom">Boom</a> <a href="/ok">OK</a>'),
                "/boom": Page(body="<p>Boom</p>"),
                "/ok": Page(body="<p>OK</p>"),
            }
        )
    )
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(
            *hooks.handlers,
            handler("boom", _boom, _write_seen),
            handler("boom too", _boom_too, _write_outputs),
        ),
    )

    result = crawl_result(server.url("/"), hooks)

    assert [
        (warning.code, warning.details["count"], warning.message) for warning in result.warnings
    ] == [
        (
            "handler_failed",
            1,
            "The handlers boom (ValueError) and boom too (KeyError) raised on "
            f"{server.url('/boom')}; the URL was recorded without their rows.",
        )
    ]


def test_a_failing_handler_does_not_stop_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/boom">Boom</a> <a href="/ok">OK</a>'),
                "/boom": Page(body="<p>Boom</p>"),
                "/ok": Page(body="<p>OK</p>"),
            }
        )
    )
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("boom", _boom, _write_seen)),
    )

    result = crawl_result(server.url("/"), hooks)

    assert (
        result.summary.state,
        [(warning.code, warning.details["count"]) for warning in result.warnings],
    ) == ("completed", [("handler_failed", 1)])


def _boom_only(result: UrlResult) -> tuple[Outputs, ...]:
    if result.url.endswith("/boom"):
        raise ValueError(result.url)
    return ()


def test_only_the_failing_handlers_rows_are_dropped(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(
            *hooks.handlers,
            handler("boom", _boom_only, _write_outputs),
            handler("seen", _seen, _write_seen),
        ),
    )

    result = crawl_result(server.url("/"), hooks)

    assert query(
        result.crawl_file,
        "SELECT urls.fetch_state, test_seen.state FROM test_seen "
        "JOIN urls ON urls.id = test_seen.url_id WHERE urls.url = ?",
        [server.url("/boom")],
    ) == [("fetched", "fetched")]


@dataclass(frozen=True, slots=True)
class Unwritable:
    url_id: int


def _unwritable(result: UrlResult) -> tuple[Unwritable, ...]:
    return (Unwritable(result.url_id),) if result.url.endswith("/boom") else ()


def _refuse(connection: Connection, rows: Sequence[Unwritable]) -> None:
    raise ValueError(f"no row for {rows[0].url_id}")


def _refuse_with_the_file(connection: Connection, rows: Sequence[Unwritable]) -> None:
    raise sqlite3.OperationalError("disk I/O error")


def _with_row_writer(writer: Callable[[Connection, Sequence[Unwritable]], None]) -> Hooks:
    hooks = default_hooks()
    return replace(
        hooks,
        handlers=(*hooks.handlers, handler("unwritable", _unwritable, writer)),
    )


def test_a_url_whose_rows_cannot_be_written_is_recorded_as_an_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(server.url("/"), _with_row_writer(_refuse))

    assert (
        query(
            result.crawl_file,
            "SELECT url, fetch_state, fetch_error FROM urls WHERE url IN (?, ?) ORDER BY id",
            [server.url("/boom"), server.url("/ok")],
        ),
        result.summary.state,
        [(warning.code, warning.details["count"]) for warning in result.warnings],
    ) == (
        [
            (server.url("/boom"), "error", "record_failed"),
            (server.url("/ok"), "fetched", None),
        ],
        "completed",
        [("record_failed", 1)],
    )


def _articles(count: int) -> Site:
    articles = range(1, count + 1)
    return Site(
        routes={
            "/": Page(body="".join(f'<a href="/p{n}">Article {n}</a>' for n in articles)),
            **{f"/p{n}": Page(body=f"<h1>Article {n}</h1>") for n in articles},
        }
    )


def _unwritable_but_the_seed(result: UrlResult) -> tuple[Unwritable, ...]:
    return () if result.url.endswith("/") else (Unwritable(result.url_id),)


def _unwritable_odd_articles(result: UrlResult) -> tuple[Unwritable, ...]:
    return (Unwritable(result.url_id),) if result.url[-1] in "13579" else ()


def test_recording_that_fails_for_every_url_fails_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_articles(120))
    hooks = default_hooks()
    hooks = replace(
        hooks, handlers=(*hooks.handlers, handler("unwritable", _unwritable_but_the_seed, _refuse))
    )

    result = crawl_result(server.url("/"), hooks)
    error = result.failure and result.failure.diagnostic

    # A bug in row code, not the disk: freeing space would not help, and the record_failed
    # warning names the first URL.
    assert (
        *_end_of(result),
        error and error.code,
        error and error.message.startswith("100 URLs in a row could not be recorded"),
        error and "record_failed" in (error.hint or "") and "resume" in (error.hint or ""),
    ) == ("failed", "write_failed", "crawl_write_failed", True, True)


@pytest.mark.parametrize(("articles", "state"), [(99, "completed"), (100, "failed")])
def test_recording_fails_the_crawl_at_100_urls_in_a_row(
    temp_workspace: TempWorkspace, fixture_site: StartSite, articles: int, state: str
) -> None:
    server = fixture_site(_articles(articles))
    hooks = default_hooks()
    hooks = replace(
        hooks, handlers=(*hooks.handlers, handler("unwritable", _unwritable_but_the_seed, _refuse))
    )

    result = crawl_result(server.url("/"), hooks)

    assert result.summary.state == state


def test_recording_that_fails_for_half_the_urls_does_not_fail_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # More failures than the limit, but a recorded URL between any two.
    server = fixture_site(_articles(220))
    hooks = default_hooks()
    hooks = replace(
        hooks, handlers=(*hooks.handlers, handler("unwritable", _unwritable_odd_articles, _refuse))
    )

    result = crawl_result(server.url("/"), hooks)

    assert (
        result.summary.state,
        [(w.code, w.details["count"]) for w in result.warnings if w.code == "record_failed"],
    ) == ("completed", [("record_failed", 110)])


def test_a_checked_url_whose_rows_cannot_be_written_is_recorded_when_it_ends_last(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # The image ends last, so its unit fails behind the final flush and its fallback unit
    # comes after that flush.
    pages = {"/": FakePage('<img src="/boom">'), "/boom": FakePage("<p>B</p>", delay=1)}

    result = crawl_result(
        "http://site.test/",
        _with_row_writer(_refuse),
        clock=clock,
        fetcher=FakeFetcher(clock, pages),
    )

    assert (
        query(result.crawl_file, "SELECT fetch_state, fetch_error FROM urls WHERE id = 2"),
        result.summary.state,
    ) == ([("error", "record_failed")], "completed")


def test_a_unit_that_fails_with_the_file_fails_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(server.url("/"), _with_row_writer(_refuse_with_the_file))
    row = crawl_row(result.crawl_file)

    assert (row["state"], row["stop_reason"], result.failure and result.failure.code) == (
        "failed",
        "write_failed",
        "crawl_write_failed",
    )


def _seen_then_boom(result: UrlResult) -> Iterator[Seen]:
    yield Seen(result.url_id, result.fetch_state)
    if result.url.endswith("/boom"):
        raise ValueError(result.url)


def test_a_handler_that_fails_midway_keeps_none_of_its_rows(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("halfway", _seen_then_boom, _write_seen)),
    )

    result = crawl_result(server.url("/"), hooks)

    assert query(
        result.crawl_file,
        "SELECT count(*) FROM test_seen JOIN urls ON urls.id = test_seen.url_id WHERE urls.url = ?",
        [server.url("/boom")],
    ) == [(0,)]


def _not_a_struct(tree: LexborHTMLParser, page: PageInput, config: None) -> Found:
    return {"url": page.url}  # type: ignore[return-value]


class Moved(msgspec.Struct, frozen=True):
    url: str
    status: int


def _found_or_moved(tree: LexborHTMLParser, page: PageInput, config: None) -> Found:
    # A branch that builds the struct of another extractor: mypy is told to look away.
    if page.url.endswith("/ok"):
        return Moved(page.url, page.status_code)  # type: ignore[return-value]
    return Found(page.url)


def test_an_extractor_that_returns_another_struct_than_it_declares_is_an_extractor_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("found", _found_or_moved, None))
    )

    assert query(
        result.crawl_file,
        "SELECT url, parsed, parse_error, parse_error_message FROM urls WHERE url IN (?, ?) "
        "ORDER BY id",
        [server.url("/"), server.url("/ok")],
    ) == [
        (server.url("/"), 1, None, None),
        (server.url("/ok"), 1, "extractor_error", "found: TypeError"),
    ]


def test_an_extractor_that_returns_no_struct_is_an_extractor_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = crawl_result(
        server.url("/"), _with_extractors(extractor("loose", _not_a_struct, None))
    )

    assert query(
        result.crawl_file,
        "SELECT parsed, parse_error, parse_error_message FROM urls WHERE url = ?",
        [server.url("/ok")],
    ) == [(1, "extractor_error", "loose: TypeError")]


@dataclass(frozen=True, slots=True)
class Flaky:
    url_id: int


def _flaky(result: UrlResult) -> tuple[Flaky, ...]:
    return (Flaky(result.url_id),) if result.crawl_depth == 0 else ()


def _write_flaky(written: list[int]) -> Callable[[Connection, Sequence[Flaky]], None]:
    def write(connection: Connection, rows: Sequence[Flaky]) -> None:
        # Fails when the writer runs the unit again, which ends the writer (017 D6).
        if written:
            raise RuntimeError("not the same twice")
        written.extend(row.url_id for row in rows)

    return write


def test_a_writer_that_ends_reports_why_it_ended(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(
            *hooks.handlers,
            handler("flaky", _flaky, _write_flaky([])),
            handler("unwritable", _unwritable, _refuse),
        ),
    )

    result = crawl_result(server.url("/"), hooks)

    assert _failed_with(result) == ("failed", "write_failed", CrawlWriterReplayError.__name__)


def test_a_url_that_meets_an_ended_writer_reports_why_the_writer_ended(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # /ok answers after the writer has ended on /boom's replay, so its own unit is refused.
    server = fixture_site(
        Site(routes={**BOOM_SITE.routes, "/ok": Page(body="<p>OK</p>", delay=0.3)})
    )
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(
            *hooks.handlers,
            handler("flaky", _flaky, _write_flaky([])),
            handler("unwritable", _unwritable, _refuse),
        ),
    )

    result = crawl_result(server.url("/"), hooks)

    assert _failed_with(result) == ("failed", "write_failed", CrawlWriterReplayError.__name__)


def _end_of(result: CrawlResult) -> tuple[str, str | None]:
    return (result.summary.state, result.summary.stop_reason)


def _failed_with(result: CrawlResult) -> tuple[str, str | None, str | None]:
    """The end, and the type of the error that ended the Crawl."""
    error = None if result.failure is None else result.failure.diagnostic.details["error"]
    return (*_end_of(result), error and error.split(":")[0])


@dataclass(frozen=True, slots=True)
class RowValues:
    url_id: int
    values: str


def _row_values(result: UrlResult) -> tuple[RowValues, ...]:
    response = result.response
    values = (
        result.fetch_state,
        None if response is None else response.status_code,
        None if response is None else response.content_type,
        result.parsed,
        result.discovered_via,
        result.found_on_url_id is not None,
        response is not None,
        response is not None,
        result.is_internal,
        result.in_scope,
    )
    return (RowValues(result.url_id, repr(values)),)


def _write_row_values(connection: Connection, rows: Sequence[RowValues]) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_values (url_id INTEGER, v TEXT)"))
    connection.execute(
        text("INSERT INTO test_values VALUES (:url_id, :v)"),
        [{"url_id": row.url_id, "v": row.values} for row in rows],
    )


def test_a_handler_gets_the_row_values_of_the_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = default_hooks()
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, handler("values", _row_values, _write_row_values)),
    )

    result = crawl_result(server.url("/"), hooks)

    assert query(
        result.crawl_file,
        "SELECT urls.url, test_values.v FROM test_values JOIN urls ON urls.id = test_values.url_id "
        "WHERE urls.url IN (?, ?) ORDER BY urls.id",
        [server.url("/"), server.url("/ok")],
    ) == [
        (
            server.url("/"),
            repr(
                (
                    *("fetched", 200, "text/html; charset=utf-8", True),
                    *("seed", False, True, True, True, True),
                )
            ),
        ),
        (
            server.url("/ok"),
            repr(
                (
                    *("fetched", 200, "text/html; charset=utf-8", True),
                    *("hyperlink", True, True, True, True, True),
                )
            ),
        ),
    ]


def _slowly(
    writer: Callable[[Connection, Sequence[Unwritable]], None],
) -> Callable[[Connection, Sequence[Unwritable]], None]:
    def write(connection: Connection, rows: Sequence[Unwritable]) -> None:
        # Still running when the engine goes on, so the failure reaches it later.
        time.sleep(0.5)
        writer(connection, rows)

    return write


@pytest.mark.slow
def test_a_check_whose_unit_fails_as_the_frontier_runs_dry_is_requested_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/boom">'),
                # Answers after the frontier has run dry, so its unit is the last one submitted.
                "/boom": Page(body="<p>B</p>", delay=0.3),
            }
        )
    )

    crawl_result(server.url("/"), _with_row_writer(_slowly(_refuse)))

    assert [request.path for request in server.requests if request.path == "/boom"] == ["/boom"]


# /boom is a check: its unit, slow to fail, is the last one the URL limit waits for.
LIMIT_SITE = Site(
    routes={
        "/": Page(body='<img src="/boom"><a href="/a">A</a><a href="/b">B</a>'),
        "/boom": Page(body="<p>B</p>"),
        "/a": Page(body="<p>A</p>"),
        "/b": Page(body="<p>B</p>"),
    }
)


@pytest.mark.slow
def test_a_file_failure_after_the_url_limit_ends_the_crawl_with_that_failure(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LIMIT_SITE)

    result = crawl_result(
        server.url("/"), _with_row_writer(_slowly(_refuse_with_the_file)), max_urls=2
    )

    assert _failed_with(result) == ("failed", "write_failed", "OperationalError")


@pytest.mark.slow
def test_a_crawl_that_failed_after_its_url_limit_gives_no_limit_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LIMIT_SITE)
    reporter = Collected()

    result = crawl_result(
        server.url("/"),
        _with_row_writer(_slowly(_refuse_with_the_file)),
        reporter=reporter,
        max_urls=2,
    )

    assert ([warning.code for warning in reporter.warnings], result.summary.state) == (
        [],
        "failed",
    )


def test_a_url_recorded_as_unwritten_keeps_its_robots_txt_verdict(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={**BOOM_SITE.routes, "/robots.txt": Robots("User-agent: *\nDisallow: /boom\n")})
    )

    result = crawl_result(server.url("/"), _with_row_writer(_refuse), ignore_robots=True)

    assert query(
        result.crawl_file,
        "SELECT fetch_error, blocked_by_robots_txt FROM urls WHERE url = ?",
        [server.url("/boom")],
    ) == [("record_failed", 1)]


def test_a_handler_without_its_writer_cannot_be_built() -> None:
    with pytest.raises(TypeError):
        handler("seen", _seen)  # type: ignore[call-arg]


def _verdict(result: UrlResult) -> tuple[Seen, ...]:
    return (Seen(result.url_id, repr(result.blocked_by_robots_txt)),)


def test_a_handler_gets_the_robots_txt_verdict_of_the_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Robots("User-agent: *\nDisallow: /private/\n"),
                "/": Page(body='<a href="/private/a">Private</a> <a href="/a">A</a>'),
                "/private/a": Page(body="<p>Private</p>"),
                "/a": Page(body="<p>A</p>"),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("verdict", _verdict, _write_seen),))

    result = crawl_result(server.url("/"), hooks, ignore_robots=True)

    assert query(
        result.crawl_file,
        "SELECT urls.url, test_seen.state FROM test_seen JOIN urls ON urls.id = test_seen.url_id "
        "ORDER BY urls.id",
    ) == [
        (server.url("/"), "False"),
        (server.url("/private/a"), "True"),
        (server.url("/a"), "False"),
    ]


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
    hooks = default_hooks()
    hooks = replace(hooks, handlers=(*hooks.handlers, handler("values", _values, _write_values)))

    crawl_file = crawl_result(server.url("/"), hooks, exclude=["/logout$"]).crawl_file

    seen = {url_id: json.loads(v) for url_id, v in query(crawl_file, "SELECT * FROM test_values")}
    recorded = {row["id"]: row for row in _urls_rows(crawl_file)}
    assert (
        sorted({values["fetch_state"] for values in seen.values()}),
        [
            (url_id, name)
            for url_id, values in seen.items()
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
    hooks = default_hooks()
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


def _x_robots_tag(result: UrlResult) -> tuple[Seen, ...]:
    if result.response is None:
        return ()
    directives = result.response.directives
    said = (directives.x_robots_tag_noindex, directives.x_robots_tag_nofollow)
    return (Seen(result.url_id, repr(said)),)


def test_a_handler_sees_the_x_robots_tag_of_a_pdf(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/report.pdf">Report</a>'),
                "/report.pdf": Page(
                    body="%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
                    content_type="application/pdf",
                    headers=[("X-Robots-Tag", "googlebot: noindex"), ("X-Robots-Tag", "nofollow")],
                ),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("directives", _x_robots_tag, _write_seen),))

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    # (noindex, nofollow): the googlebot line is for another crawler.
    assert query(
        crawl_file,
        "SELECT test_seen.state FROM test_seen JOIN urls ON urls.id = test_seen.url_id "
        "WHERE urls.url = ?",
        [server.url("/report.pdf")],
    ) == [(repr((False, True)),)]


def _always_exploding(tree: LexborHTMLParser, page: PageInput, config: None) -> Found:
    raise ValueError(page.url)


def _links(result: UrlResult) -> tuple[Seen, ...]:
    return tuple(
        Seen(result.url_id, repr((link.type, link.target, link.declared_in)))
        for link in result.links
    )


def _links_seen(crawl_file: Path, url: str) -> list[str]:
    rows = query(
        crawl_file,
        "SELECT test_seen.state FROM test_seen JOIN urls ON urls.id = test_seen.url_id "
        "WHERE urls.url = ? ORDER BY test_seen.rowid",
        [url],
    )
    return [state for (state,) in rows]


def test_a_handler_sees_the_links_of_a_page_whose_extractor_failed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/a">A</a>'), "/a": Page(body="<p>A</p>")})
    )
    hooks = replace(
        _with_extractors(extractor("exploding", _always_exploding, None)),
        handlers=(handler("links", _links, _write_seen),),
    )

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    assert _links_seen(crawl_file, server.url("/")) == [
        repr(("hyperlink", server.url("/a"), "body"))
    ]


def test_a_canonical_in_the_body_is_placed_in_the_body(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<html><head><link rel="canonical" href="/c"></head>'
                    '<body><p>Text</p><link rel="canonical" href="/d"></body></html>'
                ),
                "/c": Page(body="<p>C</p>"),
                # An error page with links, as a site's 404 template has.
                "/d": Status(404, body='<a href="/">Home</a> <a href="/e">E</a>'),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("links", _links, _write_seen),))

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    assert _links_seen(crawl_file, server.url("/")) == [
        repr(("canonical", server.url("/c"), "head")),
        repr(("canonical", server.url("/d"), "body")),
    ]
    assert _links_seen(crawl_file, server.url("/d")) == []


def _requested(result: UrlResult) -> tuple[Seen, ...]:
    return tuple(
        Seen(result.url_id, repr((link.target, link.requests_target))) for link in result.links
    )


def test_a_nofollow_link_does_not_request_its_target(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a> <a rel="nofollow" href="/b">B</a>'),
                "/a": Page(body="<p>A</p>"),
                "/b": Page(body="<p>B</p>"),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("requested", _requested, _write_seen),))

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    assert _links_seen(crawl_file, server.url("/")) == [
        repr((server.url("/a"), True)),
        repr((server.url("/b"), False)),
    ]


def _reason(result: UrlResult) -> tuple[Seen, ...]:
    return () if result.response is None else (Seen(result.url_id, result.response.reason or ""),)


def test_a_handler_sees_the_reason_phrase(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/missing">Gone</a> <a href="/old">Old</a>'),
                "/missing": Status(404),
                # As some servers word it, which no table of phrases rebuilds.
                "/old": Status(404, reason="Page Not Here"),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("reason", _reason, _write_seen),))

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    assert (
        _links_seen(crawl_file, server.url("/missing")),
        _links_seen(crawl_file, server.url("/old")),
    ) == (["Not Found"], ["Page Not Here"])


def _meta_robots(result: UrlResult) -> tuple[Seen, ...]:
    if result.response is None:
        return ()
    directives = result.response.directives
    said = (directives.meta_robots, directives.meta_robots_noindex, directives.meta_robots_nofollow)
    return (Seen(result.url_id, repr(said)),)


def test_a_handler_sees_the_robots_meta_of_a_parsed_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/draft">Draft</a>'),
                # A staging Page kept out of the index by its meta alone, with no X-Robots-Tag.
                "/draft": Page(
                    body='<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<meta name="robots" content="noindex, nofollow"><title>Draft</title></head>'
                    '<body><h1>Draft</h1><a href="/next">Next</a></body></html>'
                ),
            }
        )
    )
    hooks = replace(default_hooks(), handlers=(handler("meta", _meta_robots, _write_seen),))

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file

    assert _links_seen(crawl_file, server.url("/draft")) == [
        repr(("noindex, nofollow", True, True))
    ]
