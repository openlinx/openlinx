"""The network pause's count (020-add-crawl-core D16; seams 2, 3 and 4)."""

import io
import json
from collections import Counter
from typing import Any

import pytest

from spider.crawl.engine.pause import pause_after, probe_times
from spider.output.reporter import CliReporter, Collected
from spider.output.writer import Output
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

_TWENTY = range(1, 21)


def test_a_response_resets_the_count(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # Twenty requests without a response, but a response between any two.
    links = "".join(f'<a href="/down/{n}">Down</a><a href="/up/{n}">Up</a>' for n in _TWENTY)
    server = fixture_site(
        Site(
            routes={
                "/": Page(body=links),
                **{f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in _TWENTY},
                **{f"/up/{n}": Page(body="<p>Up</p>") for n in _TWENTY},
            }
        )
    )

    result = crawl_result(server.url("/"), concurrency=1, network_wait=0)

    assert (result.summary.state, result.counts.errors) == ("completed", 20)


def test_the_urls_of_an_internal_origin_whose_robots_txt_gets_no_response_count(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    # blog.site.test does not resolve, so its robots.txt gets no response and its URLs none.
    links = "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in _TWENTY)
    hosts = fixture_hosts(Site(routes={"/": Page(body=links)}), Site(routes={}))

    result = crawl_result(
        "http://site.test/", resolver=hosts.resolver, scope="subdomains", network_wait=0
    )

    assert (result.summary.state, result.summary.stop_reason) == ("failed", "site_unreachable")


def test_a_seed_whose_robots_txt_answers_counts_like_any_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # robots.txt answers 404, so the Seed's origin has answered before its home page resets.
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>", reset_after=0)}))

    result = crawl_result(server.url("/"), network_wait=0)

    assert (result.summary.state, result.counts.errors) == ("completed", 1)


@pytest.mark.parametrize(("concurrency", "requests"), [(1, 8), (4, 8), (5, 10), (50, 100)])
def test_the_requests_in_a_row_that_pause_the_crawl(concurrency: int, requests: int) -> None:
    assert pause_after(concurrency) == requests


@pytest.mark.parametrize(("down", "state"), [(7, "completed"), (8, "failed")])
def test_the_count_trips_at_eight_requests_in_a_row_at_concurrency_one(
    temp_workspace: TempWorkspace, fixture_site: StartSite, down: int, state: str
) -> None:
    downs = range(1, down + 1)
    links = "".join(f'<a href="/down/{n}">Down</a>' for n in downs) + '<a href="/up">Up</a>'
    server = fixture_site(
        Site(
            routes={
                "/": Page(body=links),
                **{f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in downs},
                "/up": Page(body="<p>Up</p>"),
            }
        )
    )

    result = crawl_result(server.url("/"), concurrency=1, network_wait=0)

    assert result.summary.state == state


@pytest.mark.parametrize(
    ("network_wait", "times"),
    [
        (200, (5, 10, 20, 40, 100, 160)),
        (30, (5, 10, 20)),
        # None at the wait: it would hold the Crawl past it.
        (40, (5, 10, 20)),
        (100, (5, 10, 20, 40)),
        (101, (5, 10, 20, 40, 100)),
        (4, ()),
        (0, ()),
        (1800, (5, 10, 20, 40, *range(100, 1781, 60))),
    ],
)
def test_probes_back_off_to_once_a_minute(network_wait: int, times: tuple[int, ...]) -> None:
    assert probe_times(network_wait) == times


def _dead_section() -> dict[str, FakePage]:
    """/ links to /down/1 to /down/20, which never answer, and then to /p1."""
    links = "".join(f'<a href="/down/{n}">Down {n}</a>' for n in _TWENTY) + '<a href="/p1">P1</a>'
    return {
        "/": FakePage(links),
        **{f"/down/{n}": FakePage("", fails="connection_error") for n in _TWENTY},
        "/p1": FakePage("<p>P1</p>"),
    }


def test_a_dead_section_does_not_stop_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, _dead_section()), concurrency=1
    )
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    assert (
        result.summary.state,
        {states[f"http://site.test/down/{n}"] for n in _TWENTY},
        states["http://site.test/p1"],
        [warning.code for warning in result.warnings],
    ) == ("completed", {"error"}, "fetched", ["network_paused"])


def test_network_paused_counts_the_pauses_and_their_seconds(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    # Eight failures pause it twice; the first probe, 5 seconds in, ends each pause.
    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, _dead_section()), concurrency=1
    )

    assert [w.details for w in result.warnings if w.code == "network_paused"] == [
        {"count": 2, "total_seconds": 10.0}
    ]


def test_network_paused_is_written_when_the_first_pause_begins(
    temp_workspace: TempWorkspace,
) -> None:
    clock, stderr = FakeClock(), io.BytesIO()
    reporter = CliReporter(Output(io.BytesIO(), stderr), clock)

    # Paused from one second to 41, with progress events at 10, 20, 30 and 40 seconds.
    crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, _outage_site(), outages=[(1, 30)]),
        reporter=reporter,
        concurrency=1,
    )
    lines = [json.loads(line) for line in stderr.getvalue().splitlines()]
    names = [line.get("event") or line.get("code") for line in lines]

    # An agent reading stderr learns of the pause as it begins, not 40 seconds later.
    assert names[names.index("crawl_paused") :][:3] == [
        "crawl_paused",
        "network_paused",
        "progress",
    ]


def test_a_dead_section_keeps_the_failed_robots_txt_verdict_of_its_origin(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    first, later = range(1, 9), range(9, 17)
    # blog.site.test never answers. Its first eight posts pause the Crawl; the Seed answers the
    # first probe, at 5 seconds, and /p1 answers at 6 with eight more posts.
    pages = {
        "/": FakePage(_posts(first) + '<a href="/p1">P1</a>'),
        "/p1": FakePage(_posts(later), delay=6),
        "http://blog.site.test/robots.txt": FakePage("", fails="connection_error"),
    }
    fetcher = FakeFetcher(clock, pages)

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, scope="subdomains"
    )
    blog = [url for url, _ in fetcher.starts if url.startswith("http://blog.")]

    # Asked again after the dead section, its robots.txt would fail into a second pause.
    assert (blog, result.summary.state) == (["http://blog.site.test/robots.txt"], "completed")


def _posts(numbers: range) -> str:
    return "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in numbers)


def test_probes_do_not_count_toward_the_url_limit(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    # The Seed, the twenty dead URLs and /p1 are 22 URL requests; the two probes are not.
    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, _dead_section()),
        concurrency=1,
        max_urls=22,
    )

    assert query(
        result.crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", ["http://site.test/p1"]
    ) == [("fetched",)]


def _outage_site() -> dict[str, FakePage]:
    """/ links to /p1 to /p20; /p1 answers a second later, so the outage that a test starts at
    one second begins with /p2."""
    return {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)),
        "/p1": FakePage("<p>P1</p>", delay=1),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in _TWENTY if n > 1},
    }


def _pause_events(reporter: Collected) -> list[tuple[str, dict[str, Any]]]:
    return [
        (name, data) for name, data in reporter.events if name in ("crawl_paused", "crawl_resumed")
    ]


def test_an_outage_pauses_and_resumes_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )

    assert (
        [(name, data.get("outcome")) for name, data in _pause_events(reporter)],
        result.summary.state,
    ) == ([("crawl_paused", None), ("crawl_resumed", "outage")], "completed")


def test_the_pause_events_say_why_which_urls_and_how_long(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )

    # Paused at one second by /p2 to /p9; the probes at 6, 11 and 21 fail, the one at 41 answers.
    assert _pause_events(reporter) == [
        (
            "crawl_paused",
            {
                "crawl_id": result.crawl_id,
                "reason": "connection_error",
                "urls": [f"http://site.test/p{n}" for n in range(2, 10)],
            },
        ),
        ("crawl_resumed", {"crawl_id": result.crawl_id, "duration_s": 40.0, "outcome": "outage"}),
    ]


def test_requests_that_fail_while_paused_are_requested_again_within_the_url_limit(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # Each answer, or failure, takes a little longer than the one before, so requests are still
    # in flight when the pause begins.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 31))),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=0.5 + n / 100) for n in range(1, 31)},
    }

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages, outages=[(1, 30)]),
        concurrency=4,
        max_urls=25,
    )
    requested = query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE fetch_state != 'queued' GROUP BY 1",
    )

    # 25 distinct URLs, those in flight when the pause began and the eight that made up the
    # count among them, all fetched once the outage is over.
    assert requested == [("fetched", 25)]


def test_a_url_refused_at_the_limit_before_a_pause_is_requested_once_the_count_comes_back(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 31))),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=0.5 + n / 100) for n in range(1, 31)},
    }

    # The limit refuses a request just before the eighth failure pauses the Crawl; the requests
    # still in flight then fail while paused and give their counts back, and the outage gives
    # back those of its eight, so the refused URL is requested after all.
    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages, outages=[(1, 30)]),
        concurrency=4,
        max_urls=19,
    )

    assert query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE fetch_state != 'queued' GROUP BY 1",
    ) == [("fetched", 19)]


def test_urls_that_failed_in_an_outage_are_requested_again(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)
    pages = query(
        result.crawl_file, "SELECT fetch_state, crawl_depth FROM urls WHERE url LIKE '%/p%'"
    )

    # Requested again at the depth they were found at.
    assert set(pages) == {("fetched", 1)}


def test_an_outage_requeues_a_url_once_a_run(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    # /p2 to /p9 fail until 80 seconds: requested again at 41 when the first outage ends, they
    # fail into a second outage, which ends at 81 and must not re-queue them again.
    pages = {
        **_outage_site(),
        **{f"/p{n}": FakePage("", fails="connection_error", until=80) for n in range(2, 10)},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30), (42, 80)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))
    starts = Counter(path for path, _ in fetcher.path_starts)

    # Each requested twice: at one second, and once more when the first outage ends.
    assert (
        {states[f"http://site.test/p{n}"] for n in range(2, 10)},
        {states[f"http://site.test/p{n}"] for n in range(10, 21)},
        {starts[f"/p{n}"] for n in range(2, 10)},
    ) == ({"error"}, {"fetched"}, {2})


def test_no_request_starts_while_paused(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)

    # /p2 to /p9 fail at one second and pause the Crawl; until the probe at 41 answers, only
    # the probes of / start.
    assert [(path, at) for path, at in fetcher.path_starts if 1 <= at < 41] == [
        *((f"/p{n}", 1) for n in range(2, 10)),
        ("/", 6),
        ("/", 11),
        ("/", 21),
    ]


def test_an_outage_drops_the_failed_robots_txt_verdict_of_an_internal_origin(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    posts = range(1, 9)
    # /p1 answers at one second, when the outage begins, so the blog's robots.txt fails.
    pages = {
        "/": FakePage('<a href="/p1">P1</a>'),
        "/p1": FakePage(
            "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in posts), delay=1
        ),
        **{f"http://blog.site.test/{n}": FakePage(f"<p>Post {n}</p>") for n in posts},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, scope="subdomains"
    )

    assert set(
        query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url LIKE 'http://blog.%'")
    ) == {("fetched",)}


def test_a_crawl_that_waits_longer_than_the_network_wait_fails(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # / answers at 12 seconds, and from then on nothing does: the pause begins then. Each probe
    # of / hangs for 12 seconds, as a connection that times out does, and holds the host's one
    # slot, so the probes due at 22 and 32 start as the one before ends.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY), delay=12),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in _TWENTY},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(12, float("inf"))])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, network_wait=30
    )
    probes = [at for url, at in fetcher.starts if url == "http://site.test/" and at > 0]

    # The probe that started at 41 still hangs when the wait ends at 42, so it is cancelled then.
    assert (probes, clock.monotonic(), result.summary.state, result.summary.stop_reason) == (
        [17, 29, 41],
        42,
        "failed",
        "site_unreachable",
    )


def _seed_starts(fetcher: FakeFetcher) -> list[float]:
    return [at for url, at in fetcher.starts if url == "http://site.test/"]


def test_a_seed_that_answers_late_is_crawled(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>")}, outages=[(0, 12)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher)
    seed = query(result.crawl_file, "SELECT fetch_state FROM urls WHERE id = 1")

    # The Seed's own request comes only once its robots.txt answers, after the probes at 5, 10
    # and 20 seconds; the last of them is the first to answer.
    assert (_seed_starts(fetcher), result.summary.state, seed) == (
        [5, 10, 20, 20],
        "completed",
        [("fetched",)],
    )


def test_a_seed_that_answers_the_first_probe_is_crawled(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>")}, outages=[(0, 3)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher)

    assert query(result.crawl_file, "SELECT fetch_state FROM urls WHERE id = 1") == [("fetched",)]


def test_a_seed_that_answers_late_is_crawled_within_the_url_limit(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {"/": FakePage('<a href="/a">A</a>'), "/a": FakePage("<p>A</p>")}
    fetcher = FakeFetcher(clock, pages, outages=[(0, 12)])

    # The Seed was first recorded from its failed robots.txt, without a request of its own, so
    # re-queuing it gives back no count toward the limit.
    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, max_urls=1)

    assert dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls")) == {
        "http://site.test/": "fetched",
        "http://site.test/a": "queued",
    }


def test_progress_events_say_when_the_crawl_is_paused(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    # Paused from one second to 41; /p20 then takes 30 seconds, so events come after it too.
    pages = {**_outage_site(), "/p20": FakePage("<p>P20</p>", delay=30)}
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30)])

    crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )

    assert [
        (data["elapsed_s"], data["paused"]) for name, data in reporter.events if name == "progress"
    ] == [
        (10.0, True),
        (20.0, True),
        (30.0, True),
        (40.0, True),
        (50.0, False),
        (60.0, False),
        (70.0, False),
    ]
