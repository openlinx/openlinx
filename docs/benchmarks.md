# Benchmarks

Measured capacity, and the machine each number was measured on. Benchmarks run by
hand, outside the regular CI gate and `scripts/check.py`. The TLS measurement also
uses the one-off throwaway workflow required by 022 task 6.4.

## Writer capacity

`scripts/writer_throughput.py` measures the writer's capacity, not a Crawl's ([crawl-store.md](crawl-store.md)).

- **What it does:**
  - It prepares every Page before the clock starts: 466 Link rows to 367 targets per Page, from a template's navigation, header and footer plus the Page's own Links.
  - It submits one unit per Page through `CrawlWriter.submit()`. Each unit upserts the discovered URLs, reads back their ids, updates the Page's URL row and inserts its Link rows, all through prebuilt statements.
  - A reader process queries the file during the run, and 1 unit in 997 fails half-way.
  - So that 20,000 Pages fit in memory, a Page is prepared as indexes into shared URLs and templates. Its unit builds its rows on the writer thread, so the floor includes that cost.
- **Running it:** `uv run python scripts/writer_throughput.py` on a quiet machine. It prints one JSON document and exits non-zero below its floor, or when the writer ends during the run, with the cause in the document. `--pages` sets a smaller run.
- **Its floor:** at least 12 Pages/s at 20,000 Pages, a WAL peak of at most 300 MiB and an RSS of at most 400 MiB, and the atomicity check passes: no row from a failed unit, every other Page stored.
- **Its links layout is provisional.** Its `links` table has the columns of `030`'s `links`, on a rowid table with indexes on `target_url_id` and `(type, target_url_id)`, and it exists only in its scratch crawl file. The first run against the floor, at 20,000 Pages, waits for the links benchmark to choose the layout, and restates the floor.

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
- **The result:** the hosted measurements below show extra handshake time with truststore. The operating-system trust store remains the default while the default-path decision is pending; task 6.4 remains open.

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

### Hosted runs, 2026-11-04

[Proof PR #40](https://github.com/openlinx/openlinx/pull/40) supplied the one-off TLS
workflow and was closed unmerged after the measurements and its separate
[nine-cell correctness CI](https://github.com/openlinx/openlinx/actions/runs/41816962565)
passed. [Run 41816962562](https://github.com/openlinx/openlinx/actions/runs/41816962562),
attempt 1, completed successfully on all three OSes. The measured checkout was
`232845ede757d4b3a9f46c152809b2a6b5a05478`, based on 022 checkpoint
`50cbcf6ff453c6c52487d9ddc5c07e97b5f4ca18`. The PR base was main
`82ffcce61f4e3fc800726e8690eedbc4d55b08af`; the event's synthetic merge SHA
`d5f1fd43d11d839fee02c830fff60caccfbcdf6b` was not the measured checkout.

The command was `uv run --locked python scripts/tls_handshake_speed.py --rounds 20`.
Each OS completed all five hosts, with 20 handshakes per host per store: 100 per
store and 200 per OS. No host was skipped and no measurement error was logged.
All three jobs used truststore 0.10.5, certifi 2026.10.23 and Actions runner 2.338.2.
The job's `Set up job` log records the image version and software manifest.

| OS | Architecture | Python | OpenSSL | Runner image | Image version | Job log |
|---|---|---|---|---|---|---|
| Windows Server 2025, 10.0.26100 | AMD64 | 3.14.10 | 3.5.9 | windows-2025-vs2026 | 20261030.294.1 | [Windows](https://github.com/openlinx/openlinx/actions/runs/41816962562/job/126530027421) |
| Ubuntu 26.04.1, kernel 7.0.0-1017-azure, glibc 2.43 | x86_64 | 3.14.4 | 3.5.5 | ubuntu-26.04 | 20261025.179.1 | [Linux](https://github.com/openlinx/openlinx/actions/runs/41816962562/job/126530027560) |
| macOS 26.6.2, build 25G83 | arm64 | 3.14.10 | 4.1.0 | macos-26-arm64 | 20261026.0455.2 | [macOS](https://github.com/openlinx/openlinx/actions/runs/41816962562/job/126530161212) |

The script and lock SHA256 values matched across all three jobs:

- `scripts/tls_handshake_speed.py`: `5bb693046f9868aee267b3f9c20ea9157a6719c6475b660fd26352fcca47a630`
- `uv.lock`: `12dc153f22a43a4bf5c86398e8a2da4a7b6c13be783f2af6daef97bfd5d0c678`

Context construction was measured once per store, separately from handshakes:

| OS | truststore | certifi |
|---|---|---|
| Windows | 83.4 ms | 58.7 ms |
| Linux | 1.9 ms | 7.9 ms |
| macOS | 20.8 ms | 38.9 ms |

The following cells are median / p90 handshake milliseconds, including certificate
verification and excluding TCP connection setup. Difference is the reported
truststore median minus certifi median, calculated before display rounding.
Each pooled row combines the 100 samples per store from that OS's five hosts.

#### Windows

| Host | truststore median / p90 | certifi median / p90 | Difference |
|---|---|---|---|
| www.python.org | 4.6 / 5.8 | 3.5 / 4.1 | +1.1 ms |
| github.com | 20.8 / 28.2 | 18.6 / 22.6 | +2.2 ms |
| www.wikipedia.org | 21.2 / 25.2 | 19.7 / 23.9 | +1.5 ms |
| www.cloudflare.com | 8.9 / 10.8 | 7.7 / 9.2 | +1.2 ms |
| pypi.org | 4.6 / 5.7 | 3.4 / 4.0 | +1.2 ms |
| All hosts | 8.9 / 25.0 | 7.7 / 22.4 | +1.3 ms |

#### Linux

| Host | truststore median / p90 | certifi median / p90 | Difference |
|---|---|---|---|
| www.python.org | 8.8 / 9.7 | 3.6 / 4.4 | +5.2 ms |
| github.com | 60.4 / 61.4 | 51.8 / 55.4 | +8.6 ms |
| www.wikipedia.org | 25.3 / 25.9 | 19.8 / 20.2 | +5.6 ms |
| www.cloudflare.com | 18.1 / 19.0 | 12.4 / 13.0 | +5.7 ms |
| pypi.org | 15.6 / 16.2 | 10.1 / 10.4 | +5.5 ms |
| All hosts | 18.1 / 60.4 | 12.4 / 51.8 | +5.7 ms |

#### macOS

| Host | truststore median / p90 | certifi median / p90 | Difference |
|---|---|---|---|
| www.python.org | 16.2 / 25.2 | 6.3 / 11.4 | +9.8 ms |
| github.com | 26.7 / 34.4 | 19.4 / 24.6 | +7.3 ms |
| www.wikipedia.org | 17.0 / 23.2 | 6.7 / 10.9 | +10.3 ms |
| www.cloudflare.com | 14.7 / 22.9 | 6.4 / 11.3 | +8.3 ms |
| pypi.org | 14.0 / 17.5 | 5.6 / 9.6 | +8.3 ms |
| All hosts | 16.2 / 27.1 | 6.8 / 19.5 | +9.4 ms |

All 15 host median differences were positive. On Linux and macOS, every truststore
median exceeded the corresponding certifi p90; Windows distributions overlapped
more. This is an observed difference, not a statistical significance test. The
2026-10-27 manual Windows/WSL results remain evidence for their dated environments;
they do not establish a general absence of overhead on the hosted environments.

These are single runs per OS, with truststore always first in each alternating
pair. The report contains aggregates, not raw samples, so it cannot separate an
order effect or establish repeatability. Compare the stores within each OS; pooled
absolute timings across different networks, OSes and OpenSSL versions are not
comparable evidence of a store's cost. No selective rerun or significance threshold
was used to accept these measurements.

The measurements are accepted as evidence, but task 6.4 remains open. D5's
conditional default-path change must be reconciled with the fetching spec's
requirement to use operating-system roots. Making certifi alone the default would
violate that contract. The decision is deferred; runtime truststore default and
certifi fallback remain unchanged.
