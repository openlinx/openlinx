"""The blocking warning at the CLI (020-add-crawl-core D7, crawling; seam 1)."""

from urllib.parse import urlsplit

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site, Status
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace

FLAGS = ("--rate", "--concurrency")


def _blocked(numbers: range) -> list[str]:
    return [f"/blocked/{n}" for n in numbers]


def _links_to(paths: list[str], **routes: Route) -> dict[str, Route]:
    """`/` linking to `paths` in order, each `/blocked/` path answering 403."""
    return {
        "/": Page(body="".join(f'<a href="{path}">{path}</a>' for path in paths)),
        **{path: Status(403) for path in paths if path.startswith("/blocked/")},
        **routes,
    }


def _warning_codes(*args: str) -> list[str]:
    return [warning["code"] for warning in run_cli("crawl", *args).json()["warnings"]]


def test_many_403_responses_raise_one_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes=_links_to(_blocked(range(1, 13)))))

    result = run_cli("crawl", server.url("/"))

    assert [
        (warning["code"], warning["details"], [flag in warning["hint"] for flag in FLAGS])
        for warning in result.json()["warnings"]
    ] == [
        (
            "possible_blocking",
            {"host": urlsplit(server.url("/")).hostname, "count": 10},
            [True, True],
        )
    ]


def test_a_403_of_robots_txt_does_not_count_toward_the_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A second origin of the host, whose robots.txt answers 403 after the Seed's 200: counted,
    # it would make nine own 403s ten, in any order.
    other = fixture_site(Site(routes={"/robots.txt": Status(403), "/blocked/9": Status(403)}))
    paths = [*_blocked(range(1, 9)), other.url("/blocked/9")]
    server = fixture_site(Site(routes=_links_to(paths)))

    assert _warning_codes(server.url("/")) == []


# With one request at a time, the URLs of `/` are requested in the order it links to them.


def test_a_request_without_a_response_does_not_end_the_run(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    paths = [*_blocked(range(1, 6)), "/reset", *_blocked(range(6, 11))]
    reset = Page(body="<p>" + "x" * 100_000 + "</p>", reset_after=100)
    server = fixture_site(Site(routes=_links_to(paths, **{"/reset": reset})))

    assert _warning_codes(server.url("/"), "--concurrency", "1", "--retries", "0") == [
        "possible_blocking"
    ]


def test_a_host_gets_the_warning_once_in_a_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    paths = [*_blocked(range(1, 11)), "/ok", *_blocked(range(11, 21))]
    server = fixture_site(Site(routes=_links_to(paths, **{"/ok": Page(body="<p>OK</p>")})))

    assert _warning_codes(server.url("/"), "--concurrency", "1") == ["possible_blocking"]
