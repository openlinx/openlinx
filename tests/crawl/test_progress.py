"""Progress events (020-add-crawl-core D10, crawling; fake timing)."""

from pathlib import Path
from typing import Any

from openlinx.output.reporter import Collected
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace


class CountingReporter(Collected):
    """Keeps each progress event's urls beside a count over the crawl file when it is written,
    as a reader of the file would see it then."""

    def __init__(self) -> None:
        super().__init__()
        self.crawl_file: Path | None = None
        self.counted: list[tuple[dict[str, int], dict[str, int]]] = []

    def event(self, name: str, **data: Any) -> None:
        super().event(name, **data)
        if name == "crawl_started":
            self.crawl_file = Path(data["crawl_file"])
        elif name == "progress" and self.crawl_file is not None:
            self.counted.append((data["urls"], self._counts(self.crawl_file)))

    @staticmethod
    def _counts(crawl_file: Path) -> dict[str, int]:
        states = dict(query(crawl_file, "SELECT fetch_state, count(*) FROM urls GROUP BY 1"))
        return {
            "discovered": sum(states.values()),
            "fetched": states.get("fetched", 0),
            "errors": states.get("error", 0),
            "skipped": states.get("skipped", 0),
            "queued": states.get("queued", 0),
        }


def _progress(reporter: Collected) -> list[dict[str, Any]]:
    return [data for name, data in reporter.events if name == "progress"]


def test_progress_events_come_every_10_seconds(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    # The only Page answers after 25 seconds, which ends the Crawl.
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>", delay=25)})

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter)

    assert len(_progress(reporter)) == 2


def test_progress_counts_are_those_of_the_crawl_file_when_written(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), CountingReporter()
    pages = {
        # /n is first reached through a nofollow Link, so it is recorded skipped, and /a then
        # queues it again.
        "/": FakePage('<img src="/late.html"><a href="/a">A</a><a href="/n" rel="nofollow">N</a>'),
        "/a": FakePage('<a href="/b">B</a><a href="/n">N</a>', delay=3),
        "/n": FakePage("<p>N</p>", delay=4),
        "/b": FakePage('<a href="/c">C</a>', delay=5),
        # Three deep through /a and /b, and two through the image /late.html, which answers
        # while /c is in flight and lowers its depth.
        "/c": FakePage("<p>C</p>", delay=40),
        "/late.html": FakePage('<a href="/c">C</a>', delay=25),
    }

    crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages), reporter=reporter
    )
    lowered = query(
        reporter.crawl_file or Path(), "SELECT crawl_depth FROM urls WHERE url LIKE '%/c'"
    )

    assert (
        [urls for urls, _ in reporter.counted],
        len(reporter.counted),
        lowered,
    ) == ([counted for _, counted in reporter.counted], 4, [(2,)])


def test_progress_says_how_long_the_crawl_has_run_and_its_rate(
    temp_workspace: TempWorkspace,
) -> None:
    clock, reporter = FakeClock(), Collected()
    # Six URL requests in the first 10 seconds, then none until the last Page answers.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 6))),
        **{f"/p{n}": FakePage(f"<p>{n}</p>") for n in range(1, 5)},
        "/p5": FakePage("<p>5</p>", delay=25),
    }

    crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages), reporter=reporter
    )

    assert [(event["elapsed_s"], event["rate"]) for event in _progress(reporter)] == [
        (10.0, 0.6),
        (20.0, 0.3),
    ]
