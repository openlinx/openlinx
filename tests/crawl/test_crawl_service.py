"""The Crawl Service wires 015's journal mode and redaction (020-add-crawl-core D11; seams 1, 2)."""

import json
import re
import sys
from pathlib import Path, PureWindowsPath

import pytest

from openlinx.clock import SystemClock
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlRequest, plan_crawl, start_crawl
from openlinx.services.hooks import default_hooks
from openlinx.services.settings import default_tables
from openlinx.store.records import SecretNames
from openlinx.workspace.tables import SettingsTables
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.app import EXAMPLE_TABLE, example_app
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.settings import ExampleSettings
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site(routes={"/": Page(body="<p>Home</p>")})


def test_the_journal_mode_setting_reaches_the_crawl_file(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "openlinx.toml").write_bytes(b'[store]\njournal_mode = "delete"\n')
    request = CrawlRequest(
        seed=server.url("/"),
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["linx", "crawl", server.url("/")],
        flags={},
    )

    result = start_crawl(plan_crawl(request), SystemClock(), Collected(), default_hooks())

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
    (temp_workspace.root / "openlinx.toml").write_bytes(b'[example]\ntoken = "s3cret"\n')

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


def test_a_reader_sees_a_page_a_second_after_it_was_recorded_while_another_page_loads(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage('<a href="/probe">P</a><a href="/slow">S</a>'),
        "/probe": FakePage("<p>P</p>", delay=2),
        "/slow": FakePage("<p>S</p>", delay=10),
    }
    seen: list[tuple[str, str]] = []

    def read_as_another_reader() -> None:
        (crawl_file,) = temp_workspace.home.rglob("*.sqlite")
        seen.extend(query(crawl_file, "SELECT url, fetch_state FROM urls ORDER BY id"))

    fetcher = FakeFetcher(clock, pages, on_answer={"/probe": read_as_another_reader})

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher)

    # The Seed's unit commits one second of the loop's clock after it was submitted, as it
    # would in production, though /slow keeps the clock busy until 10 s.
    assert seen == [
        ("http://site.test/", "fetched"),
        ("http://site.test/probe", "queued"),
        ("http://site.test/slow", "queued"),
    ]


def test_the_result_times_the_crawl_on_its_clock(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    # /a is found only once / has answered, so the two waits add up.
    pages = {"/": FakePage('<a href="/a">A</a>', delay=2), "/a": FakePage("<p>A</p>", delay=3)}

    result = crawl_result("http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages))

    document = result.to_json()
    assert (document["started_at"], document["ended_at"], document["duration_s"]) == (
        "2026-01-01T00:00:00.000Z",
        "2026-01-01T00:00:05.000Z",
        5.0,
    )


def _given(
    temp_workspace: TempWorkspace,
    flags: dict[str, dict[str, object]],
    *,
    seed: str = "http://site.test/",
    subdomains: bool = False,
    secret_flags: frozenset[str] = frozenset(),
) -> CrawlRequest:
    return CrawlRequest(
        seed=seed,
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["linx", "crawl", seed],
        subdomains=subdomains,
        secret_flags=secret_flags,
        flags=flags,
    )


def _with_example() -> SettingsTables:
    tables = default_tables()
    tables.register("example", EXAMPLE_TABLE)
    return tables


def test_a_refused_value_given_with_the_settings_names_its_key(
    temp_workspace: TempWorkspace,
) -> None:
    with pytest.raises(OpenLinxError) as refused:
        plan_crawl(_given(temp_workspace, {"example": {"level": "medium"}}), _with_example())

    assert (
        refused.value.code,
        refused.value.exit_code,
        refused.value.diagnostic.details.get("key"),
        "file" in refused.value.diagnostic.details,
    ) == ("invalid_value", 2, "example.level", False)


def test_a_refused_given_value_is_reported_before_a_refused_file_value(
    temp_workspace: TempWorkspace,
) -> None:
    (temp_workspace.root / "openlinx.toml").write_bytes(b'[example]\nlevel = "medium"\n')

    with pytest.raises(OpenLinxError) as refused:
        plan_crawl(_given(temp_workspace, {"crawl": {"concurrency": 0}}), _with_example())

    assert (refused.value.code, refused.value.diagnostic.details.get("key")) == (
        "invalid_value",
        "crawl.concurrency",
    )


def test_a_table_that_is_not_registered_is_named(temp_workspace: TempWorkspace) -> None:
    plan = plan_crawl(_given(temp_workspace, {}))

    with pytest.raises(
        TypeError,
        match=re.escape(
            "the settings table ExampleSettings is not registered: register it in "
            "openlinx.services.settings.default_tables()"
        ),
    ):
        plan.loaded.table(ExampleSettings)


def test_the_subdomains_shorthand_is_the_subdomains_scope_without_the_cli(
    temp_workspace: TempWorkspace,
) -> None:
    plan = plan_crawl(_given(temp_workspace, {}, subdomains=True))

    assert plan.scope.mode == "subdomains"


def test_the_subdomains_shorthand_conflicts_with_a_subfolder_scope_without_the_cli(
    temp_workspace: TempWorkspace,
) -> None:
    request = _given(
        temp_workspace,
        {"crawl": {"scope": "subfolder"}},
        seed="http://site.test/blog/",
        subdomains=True,
    )

    with pytest.raises(OpenLinxError) as conflict:
        plan_crawl(request)

    assert (conflict.value.code, conflict.value.diagnostic.details) == (
        "option_conflict",
        {"options": ["--subdomains", "--scope"]},
    )


def test_the_plan_names_the_secrets_the_crawl_file_redacts(temp_workspace: TempWorkspace) -> None:
    plan = plan_crawl(
        _given(temp_workspace, {}, secret_flags=frozenset({"--token"})), _with_example()
    )

    assert plan.new_crawl.secret_names == SecretNames(
        flags=frozenset({"--token"}), settings=frozenset({"example.token"})
    )
