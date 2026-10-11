"""The writer's throughput check, run by hand (017-speed-up-crawl-writer D11)."""

import argparse
import contextlib
import json
import multiprocessing
import os
import platform
import sqlite3
import sys
import tempfile
import threading
import time
from array import array
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any, NamedTuple

import psutil
from sqlalchemy import (
    Column,
    Connection,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    bindparam,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from spider.clock import SystemClock
from spider.output.codes import CRAWL_BUSY
from spider.output.diagnostics import SpiderError
from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.store.reading import reading
from spider.store.records import NewCrawl, SecretNames
from spider.store.types import Flag, Timestamp
from spider.store.writer import CrawlWriter
from spider.workspace.discovery import resolve_workspace

PAGES = 20_000
WINDOW_PAGES = 5_000
POISON_EVERY = 997
HOST = "https://www.site.test"
EXTERNALS = 5_000
# Each Page carries its template's navigation, header and footer Links plus its own, as the
# prototype's --template-links stream did: 466 Link rows to 367 targets per Page.
TEMPLATES = 4
TEMPLATE_TARGETS = 250
TEMPLATE_REPEATS = 80
INTERNAL_TARGETS = 104
EXTERNAL_TARGETS = 13
OWN_REPEATS = 19
# Prime: a Page's internal targets are distinct when the Page count is above INTERNAL_TARGETS
# and not a multiple of it.
INTERNAL_STRIDE = 191
LINK_ROWS_PER_PAGE = (
    TEMPLATE_TARGETS + TEMPLATE_REPEATS + INTERNAL_TARGETS + EXTERNAL_TARGETS + OWN_REPEATS
)
ANCHORS = tuple(f"Read about topic {n}" for n in range(50))

MIN_PAGES_PER_S = 12.0
MIB = 2**20
MAX_WAL_MIB = 300
MAX_RSS_MIB = 400
SAMPLE_SECONDS = 0.2
READ_PAUSE_SECONDS = 1.0

# Provisional, shaped like the prototype's (020's draft tables): they exist only in this check's
# scratch crawl file, never in the declared schema. The check moves to the schema blueprint's
# links layout when it lands.
METADATA = MetaData()
URLS = Table(
    "urls",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("url", Text, nullable=False, unique=True),
    Column("host", Text, nullable=False),
    Column("is_internal", Flag, nullable=False),
    Column("in_scope", Flag, nullable=False),
    Column("crawl_depth", Integer, nullable=False),
    Column("discovered_via", Text, nullable=False),
    Column("found_on_url_id", Integer, ForeignKey("urls.id")),
    Column("fetch_state", Text, nullable=False),
    Column("skip_reason", Text),
    Column("status_code", Integer),
    Column("content_type", Text),
    Column("response_time_ms", Integer),
    Column("fetched_at", Timestamp),
    Column("parsed", Flag, nullable=False),
    Column("size_bytes", Integer),
    Column("transferred_bytes", Integer),
    Column("attempts", Integer),
)
Index("urls_frontier", URLS.c.crawl_depth, URLS.c.id, sqlite_where=URLS.c.fetch_state == "queued")
LINKS = Table(
    "links",
    METADATA,
    Column("source_url_id", Integer, ForeignKey("urls.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("target_url_id", Integer, ForeignKey("urls.id"), nullable=False),
    Column("type", Text, nullable=False),
    Column("origin", Text, nullable=False),
    Column("element", Text),
    Column("attribute", Text),
    Column("anchor_text", Text),
    Column("alt_text", Text),
    Column("rel", Text),
    Column("rel_nofollow", Flag, nullable=False),
    Column("rel_ugc", Flag, nullable=False),
    Column("rel_sponsored", Flag, nullable=False),
    Column("hreflang", Text),
    Column("media", Text),
    Column("target_is_internal", Flag, nullable=False),
    Column("in_content_area", Flag, nullable=False),
    PrimaryKeyConstraint("source_url_id", "ordinal"),
)
Index("links_target", LINKS.c.target_url_id)
Index("links_type_target", LINKS.c.type, LINKS.c.target_url_id)

UPSERT_URLS = sqlite_insert(URLS).on_conflict_do_nothing(index_elements=["url"])
READ_IDS = select(URLS.c.url, URLS.c.id).where(URLS.c.url.in_(bindparam("urls", expanding=True)))
UPDATE_URL = update(URLS).where(URLS.c.id == bindparam("page_id"))
INSERT_LINKS = insert(LINKS)

READS = (
    "SELECT fetch_state, count(*) FROM urls GROUP BY fetch_state",
    "SELECT target_url_id, count(*) AS n FROM links GROUP BY target_url_id"
    " ORDER BY n DESC LIMIT 20",
    "SELECT source_url_id, anchor_text FROM links WHERE target_url_id = :target"
    " ORDER BY source_url_id LIMIT 50",
    "SELECT ordinal, target_url_id, type FROM links WHERE source_url_id = :source ORDER BY ordinal",
)


class Link(NamedTuple):
    # Its index in Site.urls.
    target: int
    type: str
    element: str
    attribute: str
    anchor_text: str | None
    in_content_area: bool


@dataclass(frozen=True)
class Site:
    urls: list[str]
    discovered: list[dict[str, Any]]
    templates: list[list[Link]]
    fetched: dict[str, Any]


@dataclass(frozen=True)
class Page:
    url_id: int
    template: int
    # Indexes in Site.urls of the Page's own Link targets, repeats included, in Link order.
    targets: array[int]
    poisoned: bool


def build_site(page_count: int) -> Site:
    page_urls = [
        f"{HOST}/{('news', 'shop', 'docs', 'blog')[n % 4]}/page-{n}" for n in range(page_count)
    ]
    template_urls = [
        f"{HOST}/t{t}/nav-{j}" for t in range(TEMPLATES) for j in range(TEMPLATE_TARGETS)
    ]
    external_urls = [f"https://ext{k % 50}.example/r/{k}" for k in range(EXTERNALS)]
    urls = page_urls + template_urls + external_urls
    templates: list[list[Link]] = []
    via = ["hyperlink"] * len(urls)
    for t in range(TEMPLATES):
        links: list[Link] = []
        for j in range(TEMPLATE_TARGETS):
            target = page_count + t * TEMPLATE_TARGETS + j
            if j < 10:
                link = Link(target, "css", "link", "href", None, False)
            elif j < 30:
                link = Link(target, "image", "img", "src", None, False)
            else:
                link = Link(target, "hyperlink", "a", "href", f"Section {j}", False)
            via[target] = link.type
            links.append(link)
        # The footer repeats part of the navigation.
        links += links[30 : 30 + TEMPLATE_REPEATS]
        templates.append(links)
    discovered = [
        {
            "url": url,
            "host": url.split("/")[2],
            "is_internal": url.startswith(HOST),
            "in_scope": url.startswith(HOST),
            "crawl_depth": 2,
            "discovered_via": via[index],
            "fetch_state": "queued",
            "skip_reason": None,
            "parsed": False,
        }
        for index, url in enumerate(urls)
    ]
    fetched = {
        "fetch_state": "fetched",
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "response_time_ms": 240,
        "fetched_at": datetime.now(UTC),
        "parsed": True,
        "size_bytes": 98_304,
        "transferred_bytes": 24_576,
        "attempts": 1,
    }
    return Site(urls, discovered, templates, fetched)


def prepare_pages(page_count: int) -> list[Page]:
    externals_start = page_count + TEMPLATES * TEMPLATE_TARGETS
    prepared = []
    for n in range(page_count):
        internal = [(n + 1 + k * INTERNAL_STRIDE) % page_count for k in range(INTERNAL_TARGETS)]
        external = [externals_start + (n * 13 + k) % EXTERNALS for k in range(EXTERNAL_TARGETS)]
        targets = array("l", internal + external + internal[:OWN_REPEATS])
        prepared.append(Page(n + 1, n % TEMPLATES, targets, (n + 1) % POISON_EVERY == 0))
    return prepared


def write_page(site: Site, page: Page, connection: Connection) -> None:
    links = site.templates[page.template] + [
        Link(target, "hyperlink", "a", "href", ANCHORS[(page.url_id + n) % len(ANCHORS)], True)
        for n, target in enumerate(page.targets)
    ]
    targets = list(dict.fromkeys(link.target for link in links))
    connection.execute(
        UPSERT_URLS,
        [{**site.discovered[target], "found_on_url_id": page.url_id} for target in targets],
    )
    read_back = connection.execute(READ_IDS, {"urls": [site.urls[target] for target in targets]})
    ids: dict[str, int] = dict(read_back.all())
    connection.execute(UPDATE_URL, {"page_id": page.url_id, **site.fetched})
    rows = [
        {
            "source_url_id": page.url_id,
            "ordinal": ordinal,
            "target_url_id": ids[site.urls[target]],
            "type": kind,
            "origin": "html",
            "element": element,
            "attribute": attribute,
            "anchor_text": anchor,
            "alt_text": None,
            "rel": None,
            "rel_nofollow": False,
            "rel_ugc": False,
            "rel_sponsored": False,
            "hreflang": None,
            "media": None,
            "target_is_internal": site.discovered[target]["is_internal"],
            "in_content_area": in_content,
        }
        for ordinal, (target, kind, element, attribute, anchor, in_content) in enumerate(
            links, start=1
        )
    ]
    connection.execute(INSERT_LINKS, rows)
    if page.poisoned:
        # Half-way: after its URLs, its URL update and its Links were written.
        connection.execute(INSERT_LINKS, rows[:1])


def seed_pages(site: Site, page_count: int, connection: Connection) -> None:
    METADATA.create_all(connection)
    connection.execute(
        insert(URLS),
        [
            {**site.discovered[n], "id": n + 1, "crawl_depth": 1, "found_on_url_id": None}
            for n in range(page_count)
        ],
    )


def read_while_written(path: Path, page_count: int, stop: Event, result: Path) -> None:
    reads = busy = rounds = 0
    while not stop.is_set():
        params = {
            "target": page_count + 1 + rounds % TEMPLATE_TARGETS,
            "source": 1 + rounds * 7_919 % page_count,
        }
        for sql in READS:
            try:
                with reading(path) as connection:
                    connection.execute(text(sql), params).all()
                reads += 1
            except SpiderError as error:
                if error.code != CRAWL_BUSY.code:
                    raise
                busy += 1
        rounds += 1
        stop.wait(READ_PAUSE_SECONDS)
    result.write_text(json.dumps({"reads": reads, "busy": busy}), encoding="utf-8")


class Peaks:
    def __init__(self, wal: Path) -> None:
        self.wal_bytes = 0
        self.rss_bytes = 0
        self._wal = wal
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample)

    def __enter__(self) -> "Peaks":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()

    def _sample(self) -> None:
        process = psutil.Process()
        while True:
            self.rss_bytes = max(self.rss_bytes, process.memory_info().rss)
            with contextlib.suppress(FileNotFoundError):
                self.wal_bytes = max(self.wal_bytes, self._wal.stat().st_size)
            if self._stop.wait(SAMPLE_SECONDS):
                return


def check_atomicity(path: Path, pages: list[Page], failed: set[int]) -> dict[str, Any]:
    poisoned = [page.url_id for page in pages if page.poisoned]
    with reading(path) as connection:
        rows_left: int = connection.execute(
            select(
                select(func.count())
                .select_from(LINKS)
                .where(LINKS.c.source_url_id.in_(poisoned))
                .scalar_subquery()
                + select(func.count()).where(URLS.c.found_on_url_id.in_(poisoned)).scalar_subquery()
                + select(func.count())
                .where(URLS.c.id.in_(poisoned), URLS.c.fetch_state != "queued")
                .scalar_subquery()
            )
        ).scalar_one()
        pages_stored = connection.execute(
            select(func.count()).where(URLS.c.fetch_state == "fetched")
        ).scalar_one()
        link_rows = connection.execute(select(func.count()).select_from(LINKS)).scalar_one()
    expected_pages = len(pages) - len(poisoned)
    return {
        "ok": failed == set(poisoned)
        and rows_left == 0
        and pages_stored == expected_pages
        and link_rows == expected_pages * LINK_ROWS_PER_PAGE,
        "failed_units": len(failed),
        "poisoned_units": len(poisoned),
        "rows_left_by_failed_units": rows_left,
        "pages_stored": pages_stored,
        "link_rows": link_rows,
    }


def window_rates(started: float, resolved_at: list[float]) -> list[float]:
    rates = []
    previous = started
    for start in range(0, len(resolved_at) - WINDOW_PAGES + 1, WINDOW_PAGES):
        ended = max(resolved_at[start : start + WINDOW_PAGES])
        rates.append(round(WINDOW_PAGES / (ended - previous), 1))
        previous = ended
    return rates


def machine() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpus": os.cpu_count(),
        "memory_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
    }


def measure(folder: Path, page_count: int) -> dict[str, Any]:
    workspace = resolve_workspace(cwd=folder, flag=folder, home=folder)
    crawl = create_crawl(
        NewCrawl(
            workspace=workspace,
            crawl_mode="spider",
            seeds=[f"{HOST}/"],
            command_argv=["spider", "crawl", f"{HOST}/"],
            cwd=folder,
            config={},
            secret_names=SecretNames(),
            journal_setting="auto",
        ),
        SystemClock(),
        Collected(),
    )
    site = build_site(page_count)
    pages = prepare_pages(page_count)
    resolved_at = [0.0] * page_count
    failed: set[int] = set()

    def resolved(page: Page, future: Future[None]) -> None:
        resolved_at[page.url_id - 1] = time.perf_counter()
        if future.exception() is not None:
            failed.add(page.url_id)

    spawn = multiprocessing.get_context("spawn")
    stop = spawn.Event()
    reader_result = folder / "reader.json"
    with CrawlWriter(crawl.path, SystemClock()) as writer:
        writer.run(partial(seed_pages, site, page_count))
        writer.flush()
        reader = spawn.Process(
            target=read_while_written, args=(crawl.path, page_count, stop, reader_result)
        )
        reader.start()
        with Peaks(crawl.path.with_name(crawl.path.name + "-wal")) as peaks:
            started = time.perf_counter()
            for page in pages:
                future: Future[None] = writer.submit(partial(write_page, site, page))
                future.add_done_callback(partial(resolved, page))
            writer.flush()
            elapsed = time.perf_counter() - started
        stop.set()
        reader.join()
    atomicity = check_atomicity(crawl.path, pages, failed)
    reader_counts = (
        json.loads(reader_result.read_text(encoding="utf-8")) if reader_result.exists() else {}
    )
    return {
        "machine": machine(),
        "pages": page_count,
        "link_rows_per_page": LINK_ROWS_PER_PAGE,
        "seconds": round(elapsed, 1),
        "pages_per_s": round(page_count / elapsed, 1),
        "pages_per_s_per_5k_window": window_rates(started, resolved_at),
        "link_rows_per_s": round(atomicity["link_rows"] / elapsed),
        "wal_peak_mb": round(peaks.wal_bytes / MIB, 1),
        "rss_peak_mb": round(peaks.rss_bytes / MIB, 1),
        "reader": {**reader_counts, "exit_code": reader.exitcode},
        "atomicity": atomicity,
        "below_floor": below_floor(
            page_count / elapsed,
            peaks,
            # A reader that crashed leaves no counts, only its exit code.
            reader.exitcode == 0 and reader_counts.get("reads", 0) > 0,
            atomicity["ok"],
        ),
    }


def below_floor(pages_per_s: float, peaks: Peaks, reader_read: bool, atomic: bool) -> list[str]:
    failures = []
    if pages_per_s < MIN_PAGES_PER_S:
        failures.append(f"below {MIN_PAGES_PER_S} Pages/s")
    if peaks.wal_bytes > MAX_WAL_MIB * MIB:
        failures.append(f"WAL peak above {MAX_WAL_MIB} MB")
    if peaks.rss_bytes > MAX_RSS_MIB * MIB:
        failures.append(f"RSS peak above {MAX_RSS_MIB} MB")
    if not reader_read:
        failures.append("the reader process failed or made no read, so the run had no reader")
    if not atomic:
        failures.append("atomicity check failed")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="The writer's throughput check (017 D11).")
    parser.add_argument(
        "--pages", type=int, default=PAGES, help="fewer Pages for a smoke run of the script"
    )
    page_count = parser.parse_args().pages
    if page_count <= INTERNAL_TARGETS or page_count % INTERNAL_STRIDE == 0:
        parser.error(
            f"--pages must be above {INTERNAL_TARGETS} and not a multiple of {INTERNAL_STRIDE}"
        )
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        report = measure(Path(folder), page_count)
    print(json.dumps(report, indent=2))
    sys.exit(1 if report["below_floor"] else 0)


if __name__ == "__main__":
    main()
