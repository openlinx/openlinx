"""The Crawl Service wires 015's journal mode and redaction (020-add-crawl-core D11; seams 1, 2)."""

import json
import sys
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath

import pytest

from spider.cli.app import build_app
from spider.clock import SystemClock
from spider.crawl.fetch.fetcher import FetchResult, Request
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, plan_crawl, start_crawl
from spider.services.hooks import default_hooks
from spider.store.records import SecretNames
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.app import example_app, settings_tables
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site(routes={"/": Page(body="<p>Home</p>")})


def test_the_journal_mode_setting_reaches_the_crawl_file(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "spider.toml").write_bytes(b'[store]\njournal_mode = "delete"\n')
    tables = settings_tables(build_app())
    request = CrawlRequest(
        seed=server.url("/"),
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["spider", "crawl", server.url("/")],
        secret_names=SecretNames(),
        flags={},
    )

    result = start_crawl(plan_crawl(request, tables), SystemClock(), Collected(), default_hooks())

    assert crawl_row(result.crawl_file)["journal_mode"] == "delete"


def test_the_dns_resolver_hook_reaches_the_crawl(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(HOME_PAGE, Site(routes={}))

    result = crawl_result("http://site.test/", resolver=hosts.resolver)

    assert (
        query(result.crawl_file, "SELECT url, fetch_state, status_code FROM urls"),
        [request.path for request in hosts.site.requests],
    ) == ([("http://site.test/", "fetched", 200)], ["/robots.txt", "/"])


def test_a_secret_setting_is_redacted_in_the_recorded_config(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "spider.toml").write_bytes(b'[example]\ntoken = "s3cret"\n')

    result = run_cli("crawl", server.url("/"), app=example_app())
    config = json.loads(crawl_row(Path(result.json()["crawl_file"]))["config"])

    assert config["example"] == {"level": "low", "token": "***"}


@pytest.mark.skipif(sys.platform != "win32", reason="UNC paths are Windows paths")
def test_a_journal_warning_reaches_the_result_and_the_crawl_file(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    local = PureWindowsPath(temp_workspace.root)
    # The machine's own administrative share: a real UNC path to the same folder.
    share = PureWindowsPath(f"//localhost/{local.drive[0]}$/", *local.parts[1:])

    result = run_cli("crawl", server.url("/"), "--workspace", str(share)).json()
    stored = json.loads(crawl_row(Path(result["crawl_file"]))["warnings"])

    assert (
        [warning["code"] for warning in result["warnings"]],
        [warning["code"] for warning in stored],
    ) == (["store_wal_unavailable"], ["store_wal_unavailable"])


class ReadingFetcher(FakeFetcher):
    """Reads the crawl file as another reader would, when /probe answers."""

    def __init__(self, clock: FakeClock, pages: Mapping[str, FakePage], home: Path) -> None:
        super().__init__(clock, pages)
        self._home = home
        self.seen: list[tuple[str, str]] = []

    async def fetch(self, request: Request) -> FetchResult:
        result = await super().fetch(request)
        if request.url.endswith("/probe"):
            (crawl_file,) = self._home.rglob("*.sqlite")
            self.seen = query(crawl_file, "SELECT url, fetch_state FROM urls ORDER BY id")
        return result


def test_a_reader_sees_a_page_a_second_after_it_was_recorded_while_another_page_loads(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage('<a href="/probe">P</a><a href="/slow">S</a>'),
        "/probe": FakePage("<p>P</p>", delay=2),
        "/slow": FakePage("<p>S</p>", delay=10),
    }
    fetcher = ReadingFetcher(clock, pages, temp_workspace.home)

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher)

    # The Seed's unit commits one second of the loop's clock after it was submitted, as it
    # would in production, though /slow keeps the clock busy until 10 s.
    assert fetcher.seen == [
        ("http://site.test/", "fetched"),
        ("http://site.test/probe", "queued"),
        ("http://site.test/slow", "queued"),
    ]
