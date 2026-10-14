"""The hooks of a Crawl: handlers, passes and extractors (020-add-crawl-core D9; seam 2)."""

from dataclasses import dataclass, replace
from typing import Any

import msgspec
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection, text

from spider.cli.app import build_app
from spider.crawl.hooks import Handler, Hooks, Pass, UrlResult, default_hooks
from spider.crawl.pages import Extractor, PageInput
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, CrawlResult, plan_crawl, start_crawl
from spider.store.crawls import crawl_summary
from spider.store.records import CrawlState, SecretNames
from spider.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.app import settings_tables
from tests.support.clock import FakeClock
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _crawl(temp_workspace: TempWorkspace, seed: str, hooks: Hooks, **crawl: Any) -> CrawlResult:
    request = CrawlRequest(
        seed=seed,
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["spider", "crawl", seed],
        secret_names=SecretNames(),
        flags={"crawl": crawl},
    )
    plan = plan_crawl(request, settings_tables(build_app()))
    return start_crawl(plan, FakeClock(), Collected(), hooks)


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
        handlers=(*hooks.handlers, Handler("seen", _seen)),
        row_writers={**hooks.row_writers, Seen: _write_seen},
    )

    result = _crawl(temp_workspace, server.url("/"), hooks, exclude=["/logout$"])

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


def test_post_crawl_passes_run_before_a_crawl_is_completed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    seen: list[CrawlState] = []

    async def record_state(writer: CrawlWriter) -> None:
        seen.append((await writer.run_async(crawl_summary())).state)

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("state", record_state)))

    _crawl(temp_workspace, server.url("/"), hooks)

    assert seen == ["running"]


class Found(msgspec.Struct, frozen=True):
    url: str


def _exploding(tree: LexborHTMLParser, page: PageInput) -> Found:
    if page.url.endswith("/boom"):
        raise ValueError(page.url)
    return Found(page.url)


def _found(tree: LexborHTMLParser, page: PageInput) -> Found:
    return Found(page.url)


BOOM_SITE = Site(
    routes={
        "/": Page(body='<a href="/boom">Boom</a> <a href="/ok">OK</a>'),
        "/boom": Page(body='<a href="/deeper">Deeper</a>'),
        "/ok": Page(body="<p>OK</p>"),
        "/deeper": Page(body="<p>Deeper</p>"),
    }
)


def _with_extractors(*extractors: Extractor) -> Hooks:
    hooks = default_hooks()
    return replace(hooks, extractors=(*hooks.extractors, *extractors))


def test_an_extractor_error_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = _crawl(
        temp_workspace, server.url("/"), _with_extractors(Extractor("exploding", _exploding))
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

    result = _crawl(
        temp_workspace, server.url("/"), _with_extractors(Extractor("exploding", _exploding))
    )

    assert query(
        result.crawl_file, "SELECT parsed FROM urls WHERE url = ?", [server.url("/ok")]
    ) == [(1,)]


def test_links_of_a_page_whose_extractor_failed_are_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(BOOM_SITE)

    result = _crawl(
        temp_workspace, server.url("/"), _with_extractors(Extractor("exploding", _exploding))
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
    hooks = _with_extractors(Extractor("exploding", _exploding), Extractor("found", _found))
    hooks = replace(
        hooks,
        handlers=(*hooks.handlers, Handler("outputs", _outputs)),
        row_writers={**hooks.row_writers, Outputs: _write_outputs},
    )

    result = _crawl(temp_workspace, server.url("/"), hooks)

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

    result = _crawl(
        temp_workspace, server.url("/"), _with_extractors(Extractor("exploding", _exploding))
    )

    assert [
        (warning["code"], warning["details"]["count"]) for warning in result.to_json()["warnings"]
    ] == [("parse_failed", 2)]
