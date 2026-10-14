"""A Crawl of the synthetic site checked against its manifest (026-add-parse-pool D6)."""

from pathlib import Path

from spider.cli.app import build_app
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, plan_crawl, start_crawl
from spider.services.hooks import default_hooks
from spider.store.records import SecretNames
from tests.fixture_site.synthetic.accounting import CLEAN, MISSING_OUTCOME, UrlRow, account
from tests.fixture_site.synthetic.serve import SiteProcess, Tally
from tests.fixture_site.synthetic.site import (
    LOSES_LINKS,
    MISSING,
    OUTCOMES,
    PARSED,
    Fault,
    SyntheticSite,
    page_path,
    pool_refs,
)
from tests.support.app import settings_tables
from tests.support.clock import FakeClock
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

BASE = "http://127.0.0.1:8000"
SITE = SyntheticSite(
    seed=5,
    pages=150,
    slow_seconds=0.2,
    shares=dict.fromkeys(
        (
            Fault.SERVER_ERROR,
            Fault.INVALID_UTF8,
            Fault.WRONG_CHARSET,
            Fault.UNKNOWN_CHARSET,
            Fault.MALFORMED_HTML,
            Fault.SLOW,
            Fault.NO_TITLE,
            Fault.NO_H1,
            Fault.RESET,
        ),
        0.05,
    ),
)
URL_ROWS = "SELECT url, fetch_state, fetch_error, status_code, parsed, parse_error FROM urls"


def crawled(temp_workspace: TempWorkspace, seed: str) -> Path:
    request = CrawlRequest(
        seed=seed,
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["spider", "crawl", seed],
        secret_names=SecretNames(),
        flags={},
    )
    plan = plan_crawl(request, settings_tables(build_app()))
    return start_crawl(plan, FakeClock(), Collected(), default_hooks()).crawl_file


def test_a_crawl_of_the_synthetic_site_is_accounted_for(temp_workspace: TempWorkspace) -> None:
    with SiteProcess(SITE) as site:
        crawl_file = crawled(temp_workspace, site.base_url + "/")
        tally = site.stop()

    rows = [UrlRow(*row) for row in query(crawl_file, URL_ROWS)]
    accounting = account(SITE, rows, recorded_pools={"missing"}, tally=tally)

    assert (accounting.problems, set(accounting.pages)) == (
        (),
        {CLEAN, *(fault.value for fault in SITE.shares)},
    )


def expected_rows() -> list[UrlRow]:
    """The rows a correct Crawl of SITE leaves, as the manifest's outcomes say."""
    rows = []
    missing: set[int] = set()
    for n in range(SITE.pages):
        fault = SITE.fault(n)
        outcome = PARSED if fault is None else OUTCOMES[fault]
        rows.append(UrlRow(url=BASE + page_path(n), **outcome))
        if fault not in LOSES_LINKS:
            missing |= set(dict(pool_refs(n))[MISSING])
    rows += [UrlRow(url=BASE + MISSING.url(i), **MISSING_OUTCOME) for i in sorted(missing)]
    return rows


def test_every_url_that_is_not_accounted_for_is_a_problem() -> None:
    rows = expected_rows()
    clean = next(i for i, row in enumerate(rows) if row.url == BASE + page_path(1))
    server_error = next(n for n in range(SITE.pages) if SITE.fault(n) is Fault.SERVER_ERROR)
    rows[clean] = rows[clean]._replace(fetch_state="queued", status_code=None, parsed=0)
    rows = [row for row in rows if row.url != BASE + page_path(server_error)]
    rows += [
        UrlRow(BASE + "/elsewhere", "fetched", None, 200, 1, None),
        UrlRow(BASE + "/r/i/3.jpg", "fetched", None, 200, 0, None),
    ]
    tally = Tally(
        pages_requested=SITE.pages - 1,
        pages_requested_more_than_once=2,
        resource_requests=0,
        not_found=0,
    )

    accounting = account(SITE, rows, recorded_pools={"missing"}, tally=tally)

    queued = {
        "fetch_state": "queued",
        "fetch_error": None,
        "status_code": None,
        "parsed": 0,
        "parse_error": None,
    }
    servers = accounting.pages[Fault.SERVER_ERROR.value][0]
    clean_pages = accounting.pages[CLEAN][0]
    assert accounting.problems == (
        f"{BASE}/p/1 (clean) was recorded as {queued}",
        f"{BASE}/elsewhere is no URL of the synthetic site",
        f"clean Pages: {clean_pages} of {clean_pages} recorded, {clean_pages - 1} with the "
        "expected outcome",
        f"server_error Pages: {servers - 1} of {servers} recorded, {servers - 1} with the "
        "expected outcome",
        "resource URLs: 1 recorded, 0 expected",
        f"the site served {SITE.pages - 1} of {SITE.pages} Pages",
        "2 Pages were requested twice",
    )
