"""How `spider crawl` fails (020-add-crawl-core D16, crawling; seam 1)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
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
    ) == (7, "failed", "write_failed", "crawl_write_failed", [])
