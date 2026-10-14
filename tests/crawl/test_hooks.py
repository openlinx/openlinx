"""The hooks of a Crawl: handlers, passes and extractors (020-add-crawl-core D9; seam 2)."""

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import Connection, text

from spider.cli.app import build_app
from spider.crawl.hooks import Handler, Hooks, UrlResult, default_hooks
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, CrawlResult, plan_crawl, start_crawl
from spider.store.records import SecretNames
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
