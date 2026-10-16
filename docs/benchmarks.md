# Benchmarks

Measured capacity, and the machine each number was measured on. Benchmarks run by hand, never in CI or `scripts/check.py`.

## Writer capacity

`scripts/writer_throughput.py` measures the writer's capacity, not a Crawl's ([crawl-store.md](crawl-store.md)).

- **What it does:**
  - It prepares every Page before the clock starts: 466 Link rows to 367 targets per Page, from a template's navigation, header and footer plus the Page's own Links.
  - It submits one unit per Page through `CrawlWriter.submit()`. Each unit upserts the discovered URLs, reads back their ids, updates the Page's URL row and inserts its Link rows, all through prebuilt statements.
  - A reader process queries the file during the run, and 1 unit in 997 fails half-way.
  - So that 20,000 Pages fit in memory, a Page is prepared as indexes into shared URLs and templates. Its unit builds its rows on the writer thread, so the floor includes that cost.
- **Running it:** `uv run python scripts/writer_throughput.py` on a quiet machine. It prints one JSON document and exits non-zero below its floor, or when the writer ends during the run, with the cause in the document. `--pages` sets a smaller run.
- **Its floor:** at least 12 Pages/s at 20,000 Pages, a WAL peak of at most 300 MiB and an RSS of at most 400 MiB, and the atomicity check passes: no row from a failed unit, every other Page stored.
- **Its links layout is provisional.** Its `urls` and `links` tables are drafts of `020`'s, and they exist only in its scratch crawl file. The first run against the floor, at 20,000 Pages, waits for `030`'s re-grounding on the schema blueprint's links layout, which restates the floor.

### Smoke run, 2026-10-11

A 5,000-Page run (`--pages 5000`) that proves the script. It is not a run against the floor.

- **The machine:**
  - Intel Core i5-12450H (4 performance cores with SMT plus 4 efficiency cores, 12 threads), 16 GB of RAM, WD PC SN740 NVMe SSD
  - Windows 11 Home Single Language 10.0.26200
  - Python 3.14.7 (uv-managed) with SQLite 3.53.1
- **The numbers:**

| Measure | Value |
|---|---|
| Pages | 5,000 in 292.9 s |
| Pages/s | 17.1 |
| Link rows/s | 7,947 |
| WAL peak | 76.9 MiB |
| RSS peak | 148.7 MiB |
| Reader | 760 reads, 0 busy |
| Atomicity | ok: 5 of 5 failing units failed and left 0 rows; 4,995 Pages and 2,327,670 Link rows stored |

## The ~500k crawl

`scripts/crawl_500k.py` crawls a synthetic site of up to 500,000 linked Pages and checks the run by counts (`026`, design D6). It is the benchmark of the parse pool and its soak test.

- **The site:** `tests/fixture_site/synthetic/`. It is a function of its seed and a Page's number: about 50 KB and 450 Links of every Link type per Page, five of them to 1,000 External URLs on 50 `*.test` hosts, which the crawl reaches through `020`'s DNS resolver hook, a spanning tree of `--fanout` children per Page, and a share of injected faults on leaves of the tree. It is served from its own process, which tallies the Pages it served.
- **Running it:** from the repository root, on a quiet machine:
  - `uv run python -m scripts.crawl_500k` crawls 500,000 Pages over HTTP through the Crawl Service, with no `--max-urls`
  - `--mode direct` writes the same site through the real engine, store units and writer, with no HTTP: each response is a status and a Content-Type, and page preparation is replaced by the Page model, whose Links are what preparing the Page's HTML gives (a test pins that)
  - `--pages`, `--seed`, `--fanout`, `--latency` (seconds per response) and `--concurrency` shape the run, and `--keep <empty folder>` keeps the crawl file for later queries
  - `--shares hostile` adds the Pages over the preparation deadline and the Pages that end their worker. Use it only with the parse pool: the in-process executor cannot contain them, and the end-worker extractor would end the crawl process itself. The default, `baseline`, leaves them out.
- **What it prints:** one JSON document, and a non-zero exit when the run failed. It records:
  - the machine, its power plan and AC power, and the clock speed during the run (on Windows from the `PercentProcessorPerformance` of WMI, since psutil reports only the nominal clock)
  - URLs per second, the crawl process's peak RSS and CPU time, the share of that CPU time spent in page preparation, each worker's peak RSS, the site process's CPU time and the machine's CPU use
  - the crawl file's size, each table's share with its indexes, and the WAL peak
- **What fails a run:**
  - an exception, or an interrupt (Ctrl+C reaches only the script, which stops the site in order)
  - memory that grows: the last quarter's peak RSS above the second quarter's by more than 64 MiB or 10%
  - a URL not accounted for in `urls`: each Page with its expected outcome (`parsed`, or its fault's), each URL count per kind against the site's manifest, no URL that is not the site's, and every Page served exactly once. Each External URL and each Resource is checked once and not parsed, and each amphtml, mobile or misc target is recorded as not followed.

### Check run, 2026-10-14

A 10,000-Page run of each mode (`--pages 10000`, seed 1, fanout 50, concurrency 5, the baseline shares) that checks the script. It is not the baseline of task 1.2. It ran against `020`'s groups 1 to 5, which follow hyperlinks only, so the crawl file holds the Pages and the 100 missing URLs.

- **The machine:** the one of the writer's smoke run above, on AC power, on the Balanced power plan, while other sessions shared it.
- **The numbers:**

| Measure | Crawl over HTTP | Direct |
|---|---|---|
| URLs | 10,100 in 933.4 s | 10,100 in 394.2 s |
| URLs/s | 10.8 | 25.6 |
| Crawl process CPU | 833.1 s | 366.4 s |
| Page preparation's share of it | 55.4% | none (the Page model) |
| Crawl process RSS peak | 106.1 MiB, flat | 130.3 MiB, flat |
| Site process CPU | 8.9 s | none |
| Clock speed, mean (min to max) | 1,390 MHz (1,140 to 2,960) | 1,214 MHz (1,120 to 1,500) |
| Crawl file / WAL peak | 1.8 MiB / 4.0 MiB | 1.8 MiB / 3.9 MiB |
| Checks | passed: every URL accounted for, every Page served once | passed: every URL accounted for |

- **Where direct mode's time goes,** per Page, measured on 3,000 Pages on the main thread with the store units' own statements (clock speed about 1.1 to 1.4 GHz):
  - the `urls` insert of the discovered URLs: 35.7 ms of 49.1 ms. A Page gives 392 hyperlink rows to 312 distinct URLs, of which 85 are new: 78% of the rows hit `ON CONFLICT DO NOTHING`, at about 90 µs a row.
  - the Page model and its Links: 8.6 ms; choosing the followed Links: 3.1 ms; building the rows: 0.9 ms; the URL's own update: 0.5 ms; commits: 0.5 ms
- **The ceiling of a `url` → id cache** (design D6): `--new-urls-only` inserts only URLs the process has not seen. Direct mode then wrote the same 10,100 URLs in 74.7 s, at 135.2 URLs/s against 25.6, and every URL was accounted for.
