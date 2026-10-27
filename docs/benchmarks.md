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

## TLS handshake

`scripts/tls_handshake_speed.py` compares the two trust store paths of the crawler's TLS setup ([crawling.md](crawling.md#tls)): truststore, which asks the operating system, and certifi's bundle.

- **What it does:** for each of five public hosts (www.python.org, github.com, www.wikipedia.org, www.cloudflare.com, pypi.org) it connects once to find an address that answers, then times 20 fresh TLS handshakes per trust store, alternating them, certificate verification included. A host that does not answer is named and skipped.
- **Running it:** `uv run python scripts/tls_handshake_speed.py`. `--rounds` and a list of host names change the run. It prints the median and 90th percentile handshake per host and over all hosts.
- **The result:** truststore is not measurably slower than certifi, so it stays the default path. macOS is not measured yet.

### Runs, 2026-10-27

- **The machine:** the machine of the writer's smoke run above, on a home network connection. Linux is WSL2 (kernel 6.18) on the same machine.
- **The numbers:** the median handshake over the hosts that answered.

| OS | Python | Hosts | truststore | certifi | Difference |
|---|---|---|---|---|---|
| Windows 11 | 3.14.7 | 4 | 80.7 ms | 80.0 ms | +0.7 ms |
| Windows 11 | 3.14.7 | 5 | 75.5 ms | 74.6 ms | +0.9 ms |
| Linux (WSL2) | 3.13.18 | 3 | 72.3 ms | 70.1 ms | +2.2 ms |
| Linux (WSL2) | 3.13.18 | 5 | 71.9 ms | 73.5 ms | -1.6 ms |

Per host the difference ran from -4.5 to +6.0 ms, both ways, inside the network's own spread. Building the context takes 2 to 6 ms with truststore and 24 to 28 ms with certifi, once per run.
