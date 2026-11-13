"""The network pause's count (020-add-crawl-core D16; seams 2, 3 and 4)."""

import io
import json
from collections import Counter
from typing import Any

import pytest

from openlinx.crawl.engine.pause import pause_after, probe_times
from openlinx.crawl.engine.stop import StopSignal
from openlinx.output.reporter import CliReporter, Collected
from openlinx.output.writer import Output
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
    # blog.site.test never answers. Its robots.txt fails at 0, 1 and 3 seconds, its retries
    # included, and its first eight posts pause the Crawl then; the Seed answers the first
    # probe, at 8 seconds, and /p1 answers at 9 with eight more posts.
    pages = {
        "/": FakePage(_posts(first) + '<a href="/p1">P1</a>'),
        "/p1": FakePage(_posts(later), delay=9),
        "http://blog.site.test/robots.txt": FakePage("", fails="connection_error"),
    }
    fetcher = FakeFetcher(clock, pages)

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, scope="subdomains"
    )
    blog = [url for url, _ in fetcher.starts if url.startswith("http://blog.")]

    # One request, with its two retries: asked again after the dead section, its robots.txt
    # would fail into a second pause.
    assert (blog, result.summary.state) == (["http://blog.site.test/robots.txt"] * 3, "completed")


def _posts(numbers: range) -> str:
    return "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in numbers)


def test_a_dead_subdomain_pauses_the_crawl_once(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    dead = range(1, 301)
    links = "".join(f'<a href="http://dead.site.test/{n}">Old</a>' for n in dead)
    pages = {
        "/": FakePage(links + "".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)),
        # Its robots.txt answers 404, as a front server's does when the application behind it is
        # down, so each of its URLs is requested.
        **{f"http://dead.site.test/{n}": FakePage("", fails="connection_error") for n in dead},
        # /p9 answers a second late, and the network goes down as it does.
        "/p9": FakePage("<p>P9</p>", delay=1),
    }
    # The first pause ends at 5 seconds as a dead section; the outage of the Seed's host begins
    # at 6, with /p10, and ends at 120.
    fetcher = FakeFetcher(clock, pages, outages=[(6, 120)])

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        scope="subdomains",
    )
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    # Without the exemption, the dead subdomain pauses the Crawl once per eight failures.
    assert (
        [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"],
        {states[f"http://dead.site.test/{n}"] for n in dead},
        {states[f"http://site.test/p{n}"] for n in _TWENTY},
        result.summary.state,
    ) == (["dead_section", "outage"], {"error"}, {"fetched"}, "completed")


def test_a_dead_section_on_the_seeds_host_keeps_counting(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    links = "".join(f'<a href="/down/{n}">Down</a>' for n in range(1, 9))
    pages = {
        "/": FakePage(links + "".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)),
        **{f"/down/{n}": FakePage("", fails="connection_error") for n in range(1, 9)},
        "/p9": FakePage("<p>P9</p>", delay=1),
    }
    # The probes request the Seed, so its answer never shows the Seed's origin dead: the outage
    # that begins at 6 seconds must still pause the Crawl.
    fetcher = FakeFetcher(clock, pages, outages=[(6, 120)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    assert (
        [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"],
        {states[f"http://site.test/p{n}"] for n in _TWENTY},
    ) == (["dead_section", "outage"], {"fetched"})


def test_an_answer_while_paused_leaves_the_outage_its_count(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    # /p1 is slow: it started before the network went down at one second, and answers at 31,
    # after the network came back and before the probe at 41 answers.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 31))),
        "/p1": FakePage("<p>P1</p>", delay=31),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=1) for n in range(2, 31)},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=4
    )

    assert (
        [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"],
        set(query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url LIKE '%/p%'")),
    ) == (["outage"], {("fetched",)})


def test_an_answer_while_paused_leaves_the_dead_section_its_origins(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    posts = range(1, 41)
    # blog.site.test answers its robots.txt with 404 and nothing else; site.test's pages are in
    # flight when its posts pause the Crawl, and answer half a second into the pause.
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 5)) + _posts(posts)
    pages = {
        "/": FakePage(links),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=0.5) for n in range(1, 5)},
        **{f"http://blog.site.test/{n}": FakePage("", fails="connection_error") for n in posts},
    }
    fetcher = FakeFetcher(clock, pages)

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=4,
        scope="subdomains",
    )

    assert (
        [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"],
        result.summary.state,
    ) == (["dead_section"], "completed")


def test_one_failure_inside_a_dead_origins_streak_does_not_exempt_its_origin(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    shop = range(1, 8)
    blog = range(1, 21)
    # shop.site.test is dead; one blog.site.test page times out once inside its streak. When
    # the network goes down at 11 seconds, blog's failures must still pause the Crawl.
    links = (
        "".join(f'<a href="http://shop.site.test/{n}">Shop</a>' for n in shop)
        + '<a href="http://blog.site.test/x">Blip</a>'
        + _posts(blog)
    )
    pages = {
        "/": FakePage(links),
        **{f"http://shop.site.test/{n}": FakePage("", fails="connection_error") for n in shop},
        "http://blog.site.test/x": FakePage("<p>X</p>", fails="timeout", until=1),
        # Requested beside the shop's streak, it answers at 12, once the network is down.
        "http://blog.site.test/1": FakePage("<p>1</p>", delay=12),
    }
    fetcher = FakeFetcher(clock, pages, outages=[(11, 40)])

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        scope="subdomains",
    )
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    assert (
        [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"],
        {states[f"http://blog.site.test/{n}"] for n in blog},
    ) == (["dead_section", "outage"], {"fetched"})


def test_a_forward_wall_clock_jump_does_not_turn_a_fast_probe_into_an_outage(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 9))
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": [FakePage(links), FakePage("", delay=1)],
        **{
            f"/p{n}": FakePage("<p>Recovered</p>", fails="connection_refused", until=1)
            for n in range(1, 9)
        },
    }

    def jump_at_probe_answer() -> None:
        if clock.monotonic() == 6:
            clock.shift_wall(3600)

    fetcher = FakeFetcher(clock, pages, on_answer={"/": jump_at_probe_answer})

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        network_wait=30,
    )

    assert (
        _seed_starts(fetcher)[1],
        [
            (data["outcome"], data["duration_s"])
            for name, data in reporter.events
            if name == "crawl_resumed"
        ],
        query(
            result.crawl_file,
            "SELECT fetch_state, count(*) FROM urls WHERE url LIKE '%/p%' GROUP BY fetch_state",
        ),
    ) == (5.0, [("dead_section", 6.0)], [("error", 8)])


def test_a_backward_wall_clock_jump_does_not_turn_a_late_probe_into_a_dead_section(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 9))
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": [FakePage(links), FakePage("", delay=12)],
        **{
            f"/p{n}": FakePage("<p>Recovered</p>", fails="connection_refused", until=1)
            for n in range(1, 9)
        },
    }

    def jump_at_probe_answer() -> None:
        if clock.monotonic() == 17:
            clock.shift_wall(-3600)

    fetcher = FakeFetcher(clock, pages, on_answer={"/": jump_at_probe_answer})

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        network_wait=30,
    )

    assert (
        _seed_starts(fetcher)[1],
        [
            (data["outcome"], data["duration_s"])
            for name, data in reporter.events
            if name == "crawl_resumed"
        ],
        query(
            result.crawl_file,
            "SELECT fetch_state, count(*) FROM urls WHERE url LIKE '%/p%' GROUP BY fetch_state",
        ),
    ) == (5.0, [("outage", 17.0)], [("fetched", 8)])


def test_a_first_probe_that_hangs_beyond_its_classification_window_means_an_outage(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 9))
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": [FakePage(links), FakePage("", delay=12)],
        **{
            f"/p{n}": FakePage("<p>Recovered</p>", fails="connection_refused", until=1)
            for n in range(1, 9)
        },
    }
    answers: list[float] = []
    fetcher = FakeFetcher(clock, pages, on_answer={"/": lambda: answers.append(clock.monotonic())})

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        network_wait=30,
    )

    assert _seed_starts(fetcher)[1] == 5.0
    assert answers[1] == 17.0
    assert [data["duration_s"] for name, data in reporter.events if name == "crawl_resumed"] == [
        17.0
    ]
    assert [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"] == [
        "outage"
    ]
    assert query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE url LIKE '%/p%' GROUP BY fetch_state",
    ) == [("fetched", 8)]


def test_a_first_probe_answering_exactly_at_its_classification_window_means_an_outage(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 9))
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": [FakePage(links), FakePage("", delay=5)],
        **{
            f"/p{n}": FakePage("<p>Recovered</p>", fails="connection_refused", until=1)
            for n in range(1, 9)
        },
    }
    answers: list[float] = []
    fetcher = FakeFetcher(clock, pages, on_answer={"/": lambda: answers.append(clock.monotonic())})

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        network_wait=30,
    )

    assert _seed_starts(fetcher)[1] == 5.0
    assert answers[1] == 10.0
    assert [data["duration_s"] for name, data in reporter.events if name == "crawl_resumed"] == [
        10.0
    ]
    assert [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"] == [
        "outage"
    ]
    assert query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE url LIKE '%/p%' GROUP BY fetch_state",
    ) == [("fetched", 8)]


def test_a_first_probe_held_back_by_its_host_s_retry_after_still_finds_a_dead_section(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    # /down/1 to /down/8 never answer and pause the Crawl at once, while /a, still in flight,
    # answers 429 with Retry-After: 60 at 2 seconds: the probe due at 5 is sent at 62, and the
    # Seed answers it at once.
    links = '<a href="/a">A</a>' + "".join(f'<a href="/down/{n}">D</a>' for n in range(1, 9))
    pages = {
        "/": FakePage(links),
        "/a": FakePage("", status=429, headers=(("Retry-After", "60"),), delay=2),
        **{f"/down/{n}": FakePage("", fails="connection_refused") for n in range(1, 9)},
    }

    answers: list[float] = []
    fetcher = FakeFetcher(clock, pages, on_answer={"/": lambda: answers.append(clock.monotonic())})
    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=4,
    )

    # The probe was not hung in its connection: its answer shows a dead section, not an outage.
    assert [data["outcome"] for name, data in reporter.events if name == "crawl_resumed"] == [
        "dead_section"
    ]

    assert _seed_starts(fetcher)[1] == 62.0
    assert answers[1] == 62.0
    assert [data["duration_s"] for name, data in reporter.events if name == "crawl_resumed"] == [
        62.0
    ]
    assert query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE url LIKE '%/down/%' GROUP BY fetch_state",
    ) == [("error", 8)]


def test_urls_whose_robots_txt_failed_wait_out_the_pause(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    posts = range(1, 31)
    # /p1 answers at one second with the blog's posts, as the network goes down: the blog's
    # robots.txt gets no response, and its first eight posts, recorded from that verdict,
    # pause the Crawl.
    pages = {
        "/": FakePage('<a href="/p1">P1</a>'),
        "/p1": FakePage(_posts(posts), delay=1),
        **{f"http://blog.site.test/{n}": FakePage(f"<p>Post {n}</p>") for n in posts},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=reporter,
        concurrency=1,
        scope="subdomains",
    )
    errors_while_paused = {
        data["urls"]["errors"]
        for name, data in reporter.events
        if name == "progress" and data["paused"]
    }

    # The other posts wait for the pause to end, instead of being written as errors that the
    # outage then re-queues.
    assert (
        errors_while_paused,
        set(
            query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url LIKE 'http://blog.%'")
        ),
    ) == ({8}, {("fetched",)})


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


def test_a_crawl_that_reaches_its_url_limit_during_a_network_pause_waits_for_the_pause_to_end(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 31))),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=0.5 + n / 100) for n in range(1, 31)},
    }

    # The limit refuses /p19 at 2.36 seconds, as the eight failures that pause the Crawl at
    # 2.4 still count: the outage gives their counts back, so the refused URLs come after it.
    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages, outages=[(1, 30)]),
        reporter=reporter,
        concurrency=4,
        max_urls=19,
    )
    events = [
        (name, data.get("outcome", data.get("reason")))
        for name, data in reporter.events
        if name in ("crawl_resumed", "stopping")
    ]

    assert (events, result.counts.fetched) == (
        [("crawl_resumed", "outage"), ("stopping", "max_urls")],
        19,
    )


def test_the_url_limit_s_wait_for_an_open_count_ends_at_the_network_wait(
    temp_workspace: TempWorkspace,
) -> None:
    clock, stop, stopped_at = FakeClock(), StopSignal(), []
    stop.on_first_set(lambda _: stopped_at.append(clock.monotonic()))
    # /p8 and /p9 time out at 2 seconds on every one of their 11 attempts: two failures in a
    # row, no pause, when the limit refuses /p10 at 4 seconds.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in _TWENTY},
        **{f"/p{n}": FakePage("", fails="timeout", delay=2) for n in (8, 9)},
    }

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages),
        stop=stop,
        concurrency=1,
        max_urls=10,
        network_wait=30,
        retries=10,
    )

    # The stop comes 30 seconds after the refusal, and its grace ends the retries 10 later.
    assert (result.summary.stop_reason, stopped_at, clock.monotonic()) == ("max_urls", [34], 44)


def test_the_url_limit_s_stop_does_not_end_a_network_pause(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    hosts = ("http://site.test", "http://blog.site.test", "http://shop.site.test")
    # The first URL of site.test answers at once and the others time out at 2 seconds: the limit
    # stops the Crawl at once, and the eleven requests in flight then pause it.
    links = "".join(f'<a href="{host}/{n}">{n}</a>' for n in range(1, 31) for host in hosts)
    pages = {
        "http://site.test/": FakePage(links),
        "http://site.test/1": FakePage("<p>1</p>"),
        **{
            f"{host}/{n}": FakePage("", fails="timeout", delay=2)
            for host in hosts
            for n in range(1, 31)
            if (host, n) != ("http://site.test", 1)
        },
    }

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages),
        reporter=reporter,
        scope="subdomains",
        concurrency=4,
        max_urls=13,
        timeout=2,
    )
    names = [name for name, _ in reporter.events if name in ("stopping", "crawl_paused")]

    # Ended by the stop, the pause would let their retries fail into false errors.
    assert (
        result.summary.stop_reason,
        names,
        set(query(result.crawl_file, "SELECT attempt_count FROM urls WHERE fetch_state = 'error'")),
    ) == ("max_urls", ["stopping", "crawl_paused"], {(1,)})


def test_urls_that_failed_in_an_outage_are_requested_again(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)
    pages = query(
        result.crawl_file, "SELECT fetch_state, crawl_depth FROM urls WHERE url LIKE '%/p%'"
    )

    # Requested again at the depth they were found at.
    assert set(pages) == {("fetched", 1)}


def test_an_outage_requeues_errors_recorded_before_the_pause(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)
    # DNS failures are not retried, so the first seven errors are recorded before the eighth
    # starts the pause; the Seed's probes see the same outage until clock time 30.
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": [FakePage(links), FakePage("", fails="dns_error", until=30)],
        **{f"/p{n}": FakePage("", fails="dns_error", until=30) for n in _TWENTY},
    }
    reporter = Collected()

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages),
        reporter=reporter,
        concurrency=1,
    )

    assert (
        result.summary.state,
        [data["outcome"] for name, data in _pause_events(reporter) if name == "crawl_resumed"],
        query(result.crawl_file, "SELECT fetch_state, count(*) FROM urls GROUP BY fetch_state"),
    ) == ("completed", ["outage"], [("fetched", 21)])


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


def _paused_with_a_subdomain(robots_txt: FakePage) -> dict[str, FakePage]:
    """/down/1 to /down/8 get no response, which pauses the Crawl at --concurrency 1; the
    robots.txt of sub.site.test, requested beside them, ends a second into the pause."""
    down = range(1, 9)
    links = "".join(f'<a href="/down/{n}">D</a>' for n in down)
    return {
        "/": FakePage(links + '<a href="http://sub.site.test/x">X</a>'),
        **{f"/down/{n}": FakePage("", fails="connection_error") for n in down},
        "http://sub.site.test/robots.txt": robots_txt,
        "http://sub.site.test/x": FakePage("<p>X</p>"),
    }


def test_a_url_held_at_the_pause_stays_queued_when_the_crawl_stops(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # The robots.txt of sub.site.test gets no response either, so its URL waits at the pause's
    # gate; no probe is due within the 3-second wait, so the Crawl gives up then.
    robots_txt = FakePage("", fails="connection_error", delay=1)
    fetcher = FakeFetcher(clock, _paused_with_a_subdomain(robots_txt))

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        concurrency=1,
        scope="subdomains",
        network_wait=3,
    )

    assert (
        result.summary.stop_reason,
        query(
            result.crawl_file, "SELECT fetch_state FROM urls WHERE url = 'http://sub.site.test/x'"
        ),
    ) == ("site_unreachable", [("queued",)])


def test_a_stop_cancels_the_probe_in_flight(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    stop = StopSignal()
    # / answers 30 seconds after it starts, its probes too: the pause begins at 30, and the
    # stop comes as the first probe starts at 35.
    down = range(1, 9)
    pages = {
        "/": FakePage("".join(f'<a href="/down/{n}">D</a>' for n in down), delay=30),
        **{f"/down/{n}": FakePage("", fails="connection_error") for n in down},
    }

    def stop_at_the_first_probe() -> None:
        if clock.monotonic() >= 35:
            stop.set("interrupt")

    fetcher = FakeFetcher(clock, pages, on_start={"/": stop_at_the_first_probe})

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, stop=stop, concurrency=1
    )

    assert (
        result.summary.stop_reason,
        clock.monotonic(),
        [w.details["total_seconds"] for w in result.warnings if w.code == "network_paused"],
    ) == ("interrupt", 35, [5])


def _seed_starts(fetcher: FakeFetcher) -> list[float]:
    return [at for url, at in fetcher.starts if url == "http://site.test/"]


def test_a_seed_that_answers_late_is_crawled(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>")}, outages=[(0, 12)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher)
    seed = query(result.crawl_file, "SELECT fetch_state FROM urls WHERE id = 1")

    # Its robots.txt fails at 0, 1 and 3 seconds, its retries included, which pauses the Crawl;
    # the Seed's own request comes only once its robots.txt answers, after the probes at 8 and
    # 13 seconds, the second of them the first to answer.
    assert (_seed_starts(fetcher), result.summary.state, seed) == (
        [8, 13, 13],
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
