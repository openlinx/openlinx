"""The blocking warning at the CLI (020-add-crawl-core D7, crawling; seam 1)."""

from urllib.parse import urlsplit

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site, Status
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


def _links_to_forbidden(count: int) -> dict[str, Route]:
    links = "".join(f'<a href="/blocked/{n}">{n}</a>' for n in range(1, count + 1))
    return {"/": Page(body=links), **{f"/blocked/{n}": Status(403) for n in range(1, count + 1)}}


def test_many_403_responses_raise_one_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes=_links_to_forbidden(12)))

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


FLAGS = ("--rate", "--concurrency")


def test_a_403_of_robots_txt_does_not_count_toward_the_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/robots.txt": Status(403), **_links_to_forbidden(9)}))

    result = run_cli("crawl", server.url("/"))

    assert [warning["code"] for warning in result.json()["warnings"]] == []


def test_a_request_without_a_response_does_not_end_the_run(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    paths = [f"/blocked/{n}" for n in range(1, 6)] + ["/reset"]
    paths += [f"/blocked/{n}" for n in range(6, 11)]
    routes: dict[str, Route] = {
        "/": Page(body="".join(f'<a href="{path}">{path}</a>' for path in paths)),
        "/reset": Page(body="<p>" + "x" * 100_000 + "</p>", reset_after=100),
        **{f"/blocked/{n}": Status(403) for n in range(1, 11)},
    }
    server = fixture_site(Site(routes=routes))

    # One request at a time, so the reset ends between the fifth 403 and the sixth.
    result = run_cli("crawl", server.url("/"), "--concurrency", "1")

    assert [warning["code"] for warning in result.json()["warnings"]] == ["possible_blocking"]
