"""How `spider crawl` fails (020-add-crawl-core D16, crawling; seam 1)."""

from pathlib import Path
from typing import Any

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Route, Site
from tests.support.cli import run_cli
from tests.support.crawls import crawl_row, query
from tests.support.network import closed_port
from tests.support.sqlite_faults import disk_full_after
from tests.support.workspace import TempWorkspace

# Enough Links that recording them needs more room than the full disk leaves.
_ARTICLES = range(400)
_LINKS = Site(
    routes={
        "/": Page(body="".join(f'<a href="/articles/{n}">Article {n}</a>' for n in _ARTICLES)),
        **{f"/articles/{n}": Page(body=f"<h1>Article {n}</h1>") for n in _ARTICLES},
    }
)


def test_a_write_failure_fails_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_LINKS)

    with disk_full_after(pages=16):
        result = run_cli("crawl", server.url("/"))

    assert (
        result.exit_code,
        result.json()["state"],
        result.json()["stop_reason"],
        result.stderr_json_lines()[-1]["code"],
        result.stray_stderr_lines(),
        crawl_row(Path(result.json()["crawl_file"]))["state"],
    ) == (7, "failed", "write_failed", "crawl_write_failed", [], "failed")


_DOWN = range(1, 21)


def _lost_section(*, then: str | None = None) -> Site:
    """/ links to /down/1 to /down/20, each of which sends its headers and then resets the
    connection, and then to `then`, a Page that answers."""
    links = "".join(f'<a href="/down/{n}">Down {n}</a>' for n in _DOWN)
    routes: dict[str, Route] = {
        f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in _DOWN
    }
    if then is not None:
        links += f'<a href="{then}">Then</a>'
        routes[then] = Page(body="<p>Then</p>")
    return Site(routes={"/": Page(body=links), **routes})


def test_a_network_wait_of_zero_fails_at_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_lost_section(then="/p1"))

    document = run_cli("crawl", server.url("/"), "--concurrency", "1", "--network-wait", "0").json()
    p1 = query(
        Path(document["crawl_file"]),
        "SELECT fetch_state FROM urls WHERE url = ?",
        [server.url("/p1")],
    )

    assert (document["state"], document["stop_reason"], p1) == (
        "failed",
        "site_unreachable",
        [("queued",)],
    )


def test_losing_the_site_is_reported_by_one_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(_lost_section())

    result = run_cli("crawl", server.url("/"), "--concurrency", "1", "--network-wait", "0")
    errors = result.errors()

    assert (
        result.exit_code,
        [error["code"] for error in errors],
        errors[-1:] == result.stderr_json_lines()[-1:],
        [_hint_says(error, "waited 0 seconds", "spider resume --crawl") for error in errors],
    ) == (8, ["site_unreachable"], True, [True])


def test_an_unreachable_seed_fails_the_crawl(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", f"http://127.0.0.1:{closed_port()}/", "--network-wait", "0")

    assert (result.exit_code, result.json()["state"], result.json()["stop_reason"]) == (
        8,
        "failed",
        "seed_unreachable",
    )


def test_an_unreachable_seed_is_reported_by_one_error(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", f"http://127.0.0.1:{closed_port()}/", "--network-wait", "0")
    errors = result.errors()

    # An agent's sandbox is the likeliest cause, so the hint names it, and how to go on.
    assert (
        [error["code"] for error in errors],
        errors[-1:] == result.stderr_json_lines()[-1:],
        [
            _hint_says(error, "waited 0 seconds", "sandbox", "spider resume --crawl")
            for error in errors
        ],
    ) == (["seed_unreachable"], True, [True])


def _hint_says(error: dict[str, Any], *parts: str) -> bool:
    return all(part in (error["hint"] or "") for part in parts)


def test_a_full_disk_on_the_robots_txt_row_fails_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A robots.txt of many groups, as large sites serve: its stored text overflows the disk.
    groups = "".join(f"User-agent: bot-{n}\nDisallow: /private-{n}/\n\n" for n in range(3000))
    server = fixture_site(Site(routes={"/robots.txt": Robots(groups), "/": Page(body="<p>/</p>")}))

    with disk_full_after(pages=16):
        result = run_cli("crawl", server.url("/"))

    assert (
        result.exit_code,
        result.json()["state"],
        result.stderr_json_lines()[-1]["code"],
        result.stray_stderr_lines(),
    ) == (7, "failed", "crawl_write_failed", [])
