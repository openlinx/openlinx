"""The hooks of a Crawl: handlers, passes and extractors (020-add-crawl-core D9; seam 2)."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection, text

from spider.clock import Clock
from spider.crawl.engine.hooks import Hooks, Pass, PassContext, UrlResult, handler
from spider.crawl.pages.preparation import Extractor, PageInput, extractor
from spider.output.reporter import Collected
from spider.services.hooks import default_hooks
from spider.store.crawls import crawl_summary
from spider.store.records import CrawlState
from spider.store.writer import CrawlWriterReplayError
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.sites import LATE_SHORTER_PATH, NINE_PAGES
from tests.support.workspace import TempWorkspace


@dataclass(frozen=True, slots=True)
class Seen:
    url_id: int
    fetch_state: str


def _seen(result: UrlResult) -> tuple[Seen, ...]:
    return (Seen(result.url_id, result.fetch_state),)


def _write_seen(connection: Connection, row: Seen) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_seen (url_id INTEGER, state TEXT)"))
    connection.execute(
        text("INSERT INTO test_seen VALUES (:url_id, :state)"),
        {"url_id": row.url_id, "state": row.fetch_state},
    )


def test_a_registered_handler_sees_every_url_once(
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


def test_a_post_crawl_pass_gets_the_clock_of_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    clock = FakeClock()
    clocks: list[Clock] = []

    async def record_the_clock(context: PassContext) -> None:
        clocks.append(context.clock)

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("clock", record_the_clock)))

    crawl_result(server.url("/"), hooks, clock=clock)

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


def _with_extractors(*extractors: Extractor[Any]) -> Hooks:
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


def _outputs(result: UrlResult) -> tuple[Outputs, ...]:
    return (Outputs(result.url_id, ",".join(sorted(result.outputs))),)


def _write_outputs(connection: Connection, row: Outputs) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_outputs (url_id INTEGER, names TEXT)"))
    connection.execute(
        text("INSERT INTO test_outputs VALUES (:url_id, :names)"),
        {"url_id": row.url_id, "names": row.names},
    )


def test_handlers_get_the_outputs_of_the_extractors_that_did_not_fail(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)
    hooks = _with_extractors(
        extractor("exploding", _exploding, None), extractor("found", _found, None)
    )
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


def _refuse(connection: Connection, row: Unwritable) -> None:
    raise ValueError(f"no row for {row.url_id}")


def _refuse_with_the_file(connection: Connection, row: Unwritable) -> None:
    raise sqlite3.OperationalError("disk I/O error")


def _with_row_writer(writer: Callable[[Connection, Unwritable], None]) -> Hooks:
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


def test_a_unit_that_fails_with_the_file_is_never_completed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    with pytest.raises(sqlite3.OperationalError):
        crawl_result(server.url("/"), _with_row_writer(_refuse_with_the_file))
    (crawl_file,) = temp_workspace.home.rglob("*.sqlite")

    assert crawl_row(crawl_file)["state"] == "running"


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


def _write_flaky(written: list[int]) -> Callable[[Connection, Flaky], None]:
    def write(connection: Connection, row: Flaky) -> None:
        # Fails when the writer runs the unit again, which ends the writer (017 D6).
        if written:
            raise RuntimeError("not the same twice")
        written.append(row.url_id)

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

    with pytest.raises(CrawlWriterReplayError):
        crawl_result(server.url("/"), hooks)


@dataclass(frozen=True, slots=True)
class RowValues:
    url_id: int
    values: str


def _row_values(result: UrlResult) -> tuple[RowValues, ...]:
    values = (
        result.fetch_state,
        result.status_code,
        result.content_type,
        result.parsed,
        result.discovered_via,
        result.found_on_url_id is not None,
        result.fetched_at is not None,
        result.response_time_ms is not None,
        result.is_internal,
        result.in_scope,
    )
    return (RowValues(result.url_id, repr(values)),)


def _write_row_values(connection: Connection, row: RowValues) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_values (url_id INTEGER, v TEXT)"))
    connection.execute(
        text("INSERT INTO test_values VALUES (:url_id, :v)"),
        {"url_id": row.url_id, "v": row.values},
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
    writer: Callable[[Connection, Unwritable], None],
) -> Callable[[Connection, Unwritable], None]:
    def write(connection: Connection, row: Unwritable) -> None:
        # Still running when the engine goes on, so the failure reaches it later.
        time.sleep(0.5)
        writer(connection, row)

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

    with pytest.raises(sqlite3.OperationalError):
        crawl_result(server.url("/"), _with_row_writer(_slowly(_refuse_with_the_file)), max_urls=2)


@pytest.mark.slow
def test_a_crawl_that_failed_after_its_url_limit_gives_no_limit_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LIMIT_SITE)
    reporter = Collected()

    with pytest.raises(sqlite3.OperationalError):
        crawl_result(
            server.url("/"),
            _with_row_writer(_slowly(_refuse_with_the_file)),
            reporter=reporter,
            max_urls=2,
        )

    assert [warning.code for warning in reporter.warnings] == []


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
