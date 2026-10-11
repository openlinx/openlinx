# Benchmarks

Measured capacity, and the machine each number was measured on. Benchmarks run by hand, never in CI or `scripts/check.py`.

## Writer capacity

`scripts/writer_throughput.py` measures the writer's capacity, not a Crawl's ([crawl-store.md](crawl-store.md)).

- **What it does:**
  - It prepares every Page before the clock starts: 466 Link rows to 367 targets per Page, from a template's navigation, header and footer plus the Page's own Links.
  - It submits one unit per Page through `CrawlWriter.submit()`. Each unit upserts the discovered URLs, reads back their ids, updates the Page's URL row and inserts its Link rows, all through prebuilt statements.
  - A reader process queries the file during the run, and 1 unit in 997 fails half-way.
  - So that 20,000 Pages fit in memory, a Page is prepared as indexes into shared URLs and templates. Its unit builds its rows on the writer thread, so the floor includes that cost.
- **Running it:** `uv run python scripts/writer_throughput.py` on a quiet machine. It prints one JSON document and exits non-zero below its floor. `--pages` sets a smaller run.
- **Its floor:** at least 12 Pages/s at 20,000 Pages, a WAL peak of at most 300 MB and an RSS of at most 400 MB, and the atomicity check passes: no row from a failed unit, every other Page stored.
- **Its links layout is provisional.** Its `urls` and `links` tables follow the prototype's draft tables and exist only in its scratch crawl file. The first run against the floor, at 20,000 Pages, waits for `030`'s re-grounding on the schema blueprint's links layout, which restates the floor.

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
| WAL peak | 76.9 MB |
| RSS peak | 148.7 MB |
| Reader | 760 reads, 0 busy |
| Atomicity | ok: 5 of 5 failing units failed and left 0 rows; 4,995 Pages and 2,327,670 Link rows stored |
