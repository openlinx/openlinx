"""The ~500k-Page benchmark and soak run, by hand (design D6 of 026-add-parse-pool).

Run from the repository root: `uv run python -m scripts.crawl_500k`.
"""

import argparse
import asyncio
import contextlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import msgspec
import psutil
from sqlalchemy import text

from spider.aio import loop_factory
from spider.cli.app import build_app
from spider.clock import Clock, SystemClock
from spider.crawl import pages
from spider.crawl.context import CrawlContext
from spider.crawl.engine import run_crawl
from spider.crawl.fetcher import FetchFailure, FetchResult, Request
from spider.crawl.hooks import Hooks
from spider.crawl.pages import PageSettings, PreparedPage
from spider.crawl.stop import StopSignal
from spider.crawl.urls import NormalizedUrl
from spider.crawl.warning_log import WarningLog
from spider.output.reporter import Collected
from spider.services.crawling import CrawlPlan, CrawlRequest, plan_crawl, start_crawl
from spider.services.crawls import create_crawl
from spider.services.hooks import default_hooks
from spider.store.crawls import record_state
from spider.store.reading import reading
from spider.store.records import SecretNames
from spider.store.writer import CrawlWriter
from tests.fixture_site.synthetic.accounting import URL_ROWS, UrlRow, account
from tests.fixture_site.synthetic.preparation import END_WORKER_EXTRACTOR, prepared_page
from tests.fixture_site.synthetic.serve import SiteProcess, Tally
from tests.fixture_site.synthetic.site import (
    DEFAULT_SHARES,
    HTML,
    MISSING,
    Fault,
    SyntheticSite,
    page_number,
    pool_index,
)
from tests.support.app import settings_tables

PAGES = 500_000
MIB = 2**20
SAMPLE_SECONDS = 0.5
# Memory grew when the last quarter's peak RSS is above the second quarter's by more than the
# larger of these: the first quarter warms up the caches.
GROWTH_MIB = 64
GROWTH_SHARE = 0.10
MIN_SAMPLES = 8
# The in-process executor cannot contain these: a nested Page holds the event loop for minutes,
# and the end-worker extractor would end the crawl process itself.
BASELINE_SHARES: Mapping[Fault, float] = {
    **DEFAULT_SHARES,
    Fault.NESTED_DIVS: 0.0,
    Fault.ENDS_WORKER: 0.0,
}
# 020 records every hyperlink and checks the External ones, and records amphtml, mobile and misc
# targets as not followed; Resources come with its task 9.4.
RECORDED_POOLS = frozenset({"missing", "external", "not_followed"})
DIRECT_SEED = "http://synthetic.test/"
# psutil reports only the nominal clock on Windows; this counter scales it, turbo included.
PERFORMANCE_CLASS = "Win32_PerfFormattedData_Counters_ProcessorInformation"
PERFORMANCE_SECONDS = 5
# A variable, so that the type checker of each platform reads the code of the others.
WINDOWS = sys.platform == "win32"
TABLE_BYTES = (
    "SELECT coalesce(s.tbl_name, d.name), sum(d.pgsize) FROM dbstat AS d"
    " LEFT JOIN sqlite_schema AS s ON s.name = d.name GROUP BY 1 ORDER BY 2 DESC"
)


@dataclass
class Samples:
    """What the sampler thread saw, every SAMPLE_SECONDS."""

    rss: list[tuple[float, int]] = field(default_factory=list)
    children_rss: dict[int, tuple[str, int]] = field(default_factory=dict)
    machine_cpu: list[float] = field(default_factory=list)
    clock_mhz: list[float] = field(default_factory=list)
    wal_bytes: int = 0


class Sampler:
    def __init__(self, folder: Path, exclude: set[int]) -> None:
        self.samples = Samples()
        self._folder = folder
        self._exclude = exclude
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sampler")
        self._started = 0.0

    def __enter__(self) -> "Sampler":
        self._started = time.perf_counter()
        psutil.cpu_percent()
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        process = psutil.Process()
        while not self._stop.wait(SAMPLE_SECONDS):
            samples = self.samples
            samples.rss.append((time.perf_counter() - self._started, process.memory_info().rss))
            for child in process.children(recursive=True):
                if child.pid in self._exclude:
                    continue
                with contextlib.suppress(psutil.Error):
                    name, peak = samples.children_rss.get(child.pid, (child.name(), 0))
                    samples.children_rss[child.pid] = (name, max(peak, child.memory_info().rss))
            samples.machine_cpu.append(psutil.cpu_percent())
            frequency = cpu_frequency()
            if frequency is not None:
                samples.clock_mhz.append(frequency.current)
            for wal in self._folder.rglob("*-wal"):
                with contextlib.suppress(OSError):
                    samples.wal_bytes = max(samples.wal_bytes, wal.stat().st_size)


class ProcessorPerformance:
    """The processor's speed against its nominal clock, every few seconds (Windows only)."""

    def __init__(self) -> None:
        self.percent: list[float] = []
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "ProcessorPerformance":
        powershell = shutil.which("powershell")
        if not WINDOWS or powershell is None:
            return self
        # A WMI class: its name is the same in every display language, unlike a counter path.
        command = (
            "while ($true) { [Console]::Out.WriteLine((Get-CimInstance "
            f"{PERFORMANCE_CLASS} -Filter \"Name='_Total'\").PercentProcessorPerformance); "
            f"[Console]::Out.Flush(); Start-Sleep -Seconds {PERFORMANCE_SECONDS} }}"
        )
        self._process = subprocess.Popen(
            [powershell, "-NoProfile", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._thread = threading.Thread(target=self._read, args=(self._process.stdout,))
        self._thread.start()
        return self

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    def __exit__(self, *_: object) -> None:
        if self._process is None:
            return
        self._process.terminate()
        self._process.wait()
        if self._thread is not None:
            self._thread.join()

    def _read(self, lines: Iterable[str]) -> None:
        for line in lines:
            with contextlib.suppress(ValueError):
                # The console's culture may write a decimal comma.
                self.percent.append(float(line.strip().replace(",", ".")))


class PreparationTimer:
    """The crawl process's CPU time inside page preparation, on the thread that prepares."""

    def __init__(self) -> None:
        self.seconds = 0.0

    @contextlib.contextmanager
    def installed(self) -> Iterator[None]:
        # The in-process executor looks prepare_page up at each call; 026's pool times its own.
        prepare = pages.prepare_page

        def timed(
            url: NormalizedUrl, response: FetchResult, settings: PageSettings
        ) -> PreparedPage:
            started = time.thread_time()
            try:
                return prepare(url, response, settings)
            finally:
                self.seconds += time.thread_time() - started

        pages.prepare_page = timed
        try:
            yield
        finally:
            pages.prepare_page = prepare


class ModelFetcher:
    """The direct mode's responses: a status and a Content-Type, without HTTP or a body."""

    def __init__(self, site: SyntheticSite, clock: Clock) -> None:
        self._site = site
        self._clock = clock

    async def fetch(self, request: Request) -> FetchResult | FetchFailure:
        path = urlsplit(request.url).path
        n = page_number(path, self._site.pages)
        fault = None if n is None else self._site.fault(n)
        if fault is Fault.RESET:
            # As 020's Fetcher reports a connection reset inside the body.
            return FetchFailure(
                fetch_error="connection_error",
                message="ClientPayloadError: the connection was reset",
                fetched_at=self._clock.now(),
            )
        if n is not None:
            status = 500 if fault is Fault.SERVER_ERROR else 200
            content_type = HTML
        else:
            found = pool_index(path)
            status = 404 if found is None or found[0] is MISSING else 200
            content_type = HTML if found is None else found[0].content_type
        return FetchResult(
            status_code=status,
            headers=(("Content-Type", content_type),),
            body=b"",
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )


class ModelExecutor:
    """The direct mode's page preparation: the Page model, never the HTML (design D6)."""

    backlog = 0
    # It prepares in the crawl process.
    workers = 0

    def __init__(self, site: SyntheticSite, *, new_urls_only: bool) -> None:
        self._site = site
        self._settings: PageSettings | None = None
        # The ceiling of 026 D6's url -> id cache: a Link to a URL this process has seen
        # already never reaches the insert. Bench-only; the urls rows come out the same.
        self._seen: set[str] | None = set() if new_urls_only else None

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        if self._settings is None:
            raise RuntimeError("the model executor prepares a Page before it is started")
        page = prepared_page(self._site, url, self._settings)
        seen = self._seen
        if seen is None:
            return page
        # Only the URLs earlier Pages recorded, which the insert's ON CONFLICT would drop: within
        # a Page, 020's discovery chooses between a URL's Links itself.
        links = tuple(link for link in page.links if link.target not in seen)
        seen.update(link.target for link in page.links)
        return msgspec.structs.replace(page, links=links)

    async def close(self) -> None:
        pass


def plan(folder: Path, seed: str, concurrency: int) -> CrawlPlan:
    request = CrawlRequest(
        seed=seed,
        cwd=folder,
        home=folder,
        workspace=folder,
        command_argv=["spider", "crawl", seed, "--concurrency", str(concurrency)],
        secret_names=SecretNames(),
        flags={"crawl": {"concurrency": concurrency}},
    )
    return plan_crawl(request, settings_tables(build_app()))


def benchmark_hooks() -> Hooks:
    hooks = default_hooks()
    return replace(hooks, extractors=(*hooks.extractors, END_WORKER_EXTRACTOR))


def crawl(folder: Path, served: SiteProcess, concurrency: int) -> Path:
    crawl_plan = plan(folder, served.base_url + "/", concurrency)
    result = start_crawl(
        crawl_plan, SystemClock(), Collected(), benchmark_hooks(), resolver=served.resolver()
    )
    return result.crawl_file


def direct(folder: Path, site: SyntheticSite, concurrency: int, *, new_urls_only: bool) -> Path:
    crawl_plan = plan(folder, DIRECT_SEED, concurrency)
    clock = SystemClock()
    log = WarningLog(Collected())
    crawl_file = create_crawl(crawl_plan.new_crawl, clock, log)

    async def run() -> None:
        with CrawlWriter(crawl_file.path, clock) as writer:
            context = CrawlContext(
                crawl_file=crawl_file,
                settings=crawl_plan.settings,
                scope=crawl_plan.scope,
                clock=clock,
                reporter=log,
                writer=writer,
                fetcher=ModelFetcher(site, clock),
                pages=ModelExecutor(site, new_urls_only=new_urls_only),
                hooks=benchmark_hooks(),
                stop=StopSignal(),
            )
            await run_crawl(context, crawl_plan.seed)
            if context.stop.is_set:
                raise context.stop.cause or RuntimeError(f"stopped: {context.stop.reason}")
            # Before completed, as the Crawl Service runs them: 040 reads completed as
            # "its Issues are materialised".
            for crawl_pass in context.hooks.passes:
                await crawl_pass.run(writer)
            await writer.run_async(record_state("completed", clock.now()))

    asyncio.run(run(), loop_factory=loop_factory)
    return crawl_file.path


def url_rows(crawl_file: Path) -> Iterator[UrlRow]:
    with reading(crawl_file) as connection:
        for row in connection.execute(text(URL_ROWS)):
            yield UrlRow(*row)


def file_sizes(crawl_file: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"{crawl_file.as_uri()}?mode=ro", uri=True)
    try:
        tables = connection.execute(TABLE_BYTES).fetchall()
    finally:
        connection.close()
    total = crawl_file.stat().st_size
    return {
        "file_mib": round(total / MIB, 1),
        "tables": {
            name: {"mib": round(size / MIB, 1), "share": round(size / total, 3)}
            for name, size in tables
        },
    }


def memory_growth(rss: list[tuple[float, int]]) -> dict[str, Any]:
    end = rss[-1][0] if rss else 0.0
    second = [size for at, size in rss if end * 0.25 <= at < end * 0.5]
    last = [size for at, size in rss if at >= end * 0.75]
    # A sampler that died, or a run too short to tell, must not pass as flat.
    if len(rss) < MIN_SAMPLES or not second or not last:
        return {"checked": False, "grew": None, "samples": len(rss)}
    growth = max(last) - max(second)
    return {
        "checked": True,
        "grew": growth > max(GROWTH_MIB * MIB, GROWTH_SHARE * max(second)),
        "second_quarter_peak_mib": round(max(second) / MIB, 1),
        "last_quarter_peak_mib": round(max(last) / MIB, 1),
        "samples": len(rss),
    }


def power_plan() -> str | None:
    powercfg = shutil.which("powercfg")
    if powercfg is None:
        return None
    # The console's code page, which "oem" names on Windows.
    output = subprocess.run(
        [powercfg, "/getactivescheme"],
        capture_output=True,
        encoding="oem",
        errors="replace",
        check=False,
    ).stdout
    return output.strip() or None


def cpu_frequency() -> Any:
    """psutil's clock reading, or None where the OS reports none, as on some Linux VMs."""
    try:
        return psutil.cpu_freq()
    except (NotImplementedError, OSError):
        return None


def machine() -> dict[str, Any]:
    frequency = cpu_frequency()
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": os.cpu_count(),
        "memory_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "power_plan": power_plan(),
        "on_ac_power": None if battery is None else battery.power_plugged,
        "clock_mhz": frequency._asdict(),
    }


def summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "min": round(min(values), 1),
        "mean": round(sum(values) / len(values), 1),
        "max": round(max(values), 1),
    }


def cpu_seconds(process: psutil.Process) -> float:
    times = process.cpu_times()
    return times.user + times.system


def measure(
    folder: Path, site: SyntheticSite, mode: str, concurrency: int, *, new_urls_only: bool
) -> dict[str, Any]:
    process = psutil.Process()
    timer = PreparationTimer()
    failures: list[str] = []
    tally: Tally | None = None
    site_cpu: float | None = None
    crawl_file: Path | None = None
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    frequency = cpu_frequency()
    nominal = None if frequency is None else frequency.max or frequency.current
    with contextlib.ExitStack() as stack:
        served = stack.enter_context(SiteProcess(site)) if mode == "crawl" else None
        site_process = None if served is None else psutil.Process(served.pid)
        performance = stack.enter_context(ProcessorPerformance())
        # Children of the script that are not the crawl's own: its workers are the rest.
        others = {pid for pid in (performance.pid, served and served.pid) if pid}
        sampler = stack.enter_context(Sampler(folder, others))
        stack.enter_context(timer.installed())
        cpu_before = cpu_seconds(process)
        started = time.perf_counter()
        try:
            if served is None:
                crawl_file = direct(folder, site, concurrency, new_urls_only=new_urls_only)
            else:
                crawl_file = crawl(folder, served, concurrency)
        except Exception as error:
            failures.append(f"the run failed: {type(error).__name__}: {error}")
        # The site process ignores Ctrl+C, so it is stopped in order below.
        except KeyboardInterrupt:
            failures.append("the run was interrupted")
        elapsed = time.perf_counter() - started
        crawl_cpu = cpu_seconds(process) - cpu_before
        if served is not None and site_process is not None:
            try:
                site_cpu = cpu_seconds(site_process)
                tally = served.stop()
            # The report still comes out: the failure is part of it.
            except (psutil.Error, RuntimeError, EOFError, OSError) as error:
                failures.append(f"the site process failed: {type(error).__name__}: {error}")
    samples = sampler.samples
    report: dict[str, Any] = {
        "started_at": started_at,
        "machine": machine(),
        "run": {
            "mode": mode,
            "concurrency": concurrency,
            "new_urls_only": new_urls_only,
            **{k: v for k, v in site.manifest().items() if k not in {"faults", "outcomes"}},
        },
        "seconds": round(elapsed, 1),
        "crawl_process": {
            "rss_peak_mib": round(max((size for _, size in samples.rss), default=0) / MIB, 1),
            "cpu_seconds": round(crawl_cpu, 1),
            "page_preparation_cpu_seconds": round(timer.seconds, 1),
            "page_preparation_share": round(timer.seconds / crawl_cpu, 3) if crawl_cpu else None,
        },
        "workers": [
            {"pid": pid, "name": name, "rss_peak_mib": round(peak / MIB, 1)}
            for pid, (name, peak) in samples.children_rss.items()
        ],
        "site_process_cpu_seconds": None if site_cpu is None else round(site_cpu, 1),
        "machine_cpu_percent": summary(samples.machine_cpu),
        "processor_performance_percent": summary(performance.percent),
        "clock_mhz": summary(
            [nominal * percent / 100 for percent in performance.percent]
            if performance.percent and nominal
            else samples.clock_mhz
        ),
        "wal_peak_mib": round(samples.wal_bytes / MIB, 1),
        "memory": memory_growth(samples.rss),
        "tally": None if tally is None else asdict(tally),
    }
    if not report["memory"]["checked"]:
        failures.append(
            f"too few memory samples ({report['memory']['samples']}) to tell whether memory grew"
        )
    elif report["memory"]["grew"]:
        failures.append("the crawl process's memory grew")
    if crawl_file is not None:
        origin = DIRECT_SEED.rstrip("/") if served is None else served.base_url
        accounting = account(
            site,
            url_rows(crawl_file),
            origin=origin,
            recorded_pools=RECORDED_POOLS,
            tally=tally,
        )
        urls = sum(recorded for _, recorded, _ in accounting.pages.values()) + sum(
            recorded for _, recorded in accounting.pools.values()
        )
        report |= {
            "urls": urls,
            "urls_per_s": round(urls / elapsed, 1),
            "crawl_file": {"path": str(crawl_file), **file_sizes(crawl_file)},
            "accounting": accounting.to_json(),
        }
        failures += accounting.problems
    report["failures"] = failures
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="The ~500k-Page benchmark (026 design D6).")
    parser.add_argument("--pages", type=int, default=PAGES)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fanout", type=int, default=50)
    parser.add_argument("--latency", type=float, default=0.0, help="seconds per response")
    parser.add_argument("--concurrency", type=int, default=5, choices=range(1, 51))
    parser.add_argument(
        "--mode",
        choices=("crawl", "direct"),
        default="crawl",
        help="crawl over HTTP, or write the Page models through the store with no HTTP",
    )
    parser.add_argument(
        "--shares",
        choices=("baseline", "hostile"),
        default="baseline",
        help="hostile adds the Pages over the deadline and those that end their worker",
    )
    parser.add_argument(
        "--new-urls-only",
        action="store_true",
        help="direct mode: insert only URLs not seen before, the ceiling of a url -> id cache",
    )
    parser.add_argument(
        "--keep", type=Path, help="an empty folder to keep the crawl file in, for later queries"
    )
    args = parser.parse_args()
    if args.new_urls_only and args.mode != "direct":
        parser.error("--new-urls-only needs --mode direct")
    site = SyntheticSite(
        seed=args.seed,
        pages=args.pages,
        fanout=args.fanout,
        latency=args.latency,
        shares=BASELINE_SHARES if args.shares == "baseline" else DEFAULT_SHARES,
    )
    with contextlib.ExitStack() as stack:
        if args.keep is None:
            folder = Path(
                stack.enter_context(tempfile.TemporaryDirectory(ignore_cleanup_errors=True))
            )
        else:
            folder = args.keep
            folder.mkdir(parents=True, exist_ok=True)
            if any(folder.iterdir()):
                parser.error(f"--keep {folder} is not empty")
        report = measure(
            folder, site, args.mode, args.concurrency, new_urls_only=args.new_urls_only
        )
    print(json.dumps(report, indent=2))
    sys.exit(1 if report["failures"] else 0)


if __name__ == "__main__":
    main()
