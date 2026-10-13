> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** (its groups 4 and later, page preparation and the executor seam among them, are not coded yet; this draft follows its design):
  - **Page preparation** (`020` D9) is one pure, picklable function of a fetched response (its bytes, headers and URL) plus a frozen settings snapshot (the robots token, `--strip-params`, the `ScopeRules`, and the settings that registered extractors read, such as `030`'s `content_area`). It decodes, parses once, runs the link extractor, the registered extractors and the robots directives parser, and returns one frozen msgspec record.
  - **The executor seam:** the engine calls `await prepare(response)` through the page executor of the `CrawlContext` (`020` D15). `020` ships the in-process executor; this change plugs a process pool in behind the same seam without touching the engine.
  - **`Hooks`** (`020` D9) is a frozen dataclass of tuples in the `CrawlContext`: extractors, per-response handlers and post-crawl passes, listed by `default_hooks()`. Extractors are module-level functions from the parsed tree and a `PageInput` to a msgspec struct, so a worker process imports them by name. Per-response handlers turn a `UrlResult` into store rows; they run in the crawl process for every URL that reaches a final state, so they stay there. A test adds its own extractors and handlers to `default_hooks()` and passes them to the Crawl Service.
  - **The link extractor** returns `DiscoveredLink` values with a non-nullable normalised target (a malformed reference is dropped) and an `ordinal`, the Link's place in document order. It takes an `is_internal: Callable[[NormalizedUrl], bool]` and imports nothing of the Scope; page preparation passes the one built from the snapshot's `ScopeRules`.
  - **`ScopeRules`** holds strings only and pickles to about 134 bytes. The Public Suffix List behind `subdomains` is loaded lazily, once per process, on the first lookup (about 56 ms), so each worker that needs it loads it once.
  - **`parse_error`** already lists `worker_crashed` for this change (`020` D18), and the `StopSignal` gives requests in flight a grace period.
- **ADR-0006:** the records that cross the pool are frozen `msgspec.Struct`s (`DiscoveredLink`, `PageInput`, extractor outputs and the page-preparation record). They cross the process boundary as they are, and pickle about twice as fast as slotted dataclasses.
- **Platforms:** Windows only has `spawn`. Python 3.14 changes the default start method on Linux to `forkserver`. `fork` in a process with threads is unsafe on macOS.
- **`060-add-crawl-control`** starts background Crawls with CREATE_NO_WINDOW, which is approved.
- **The pool is unconditional in v0.1** (the user's decision of 2026-10-11). The benchmark measures and sizes it; it does not decide whether it is built.

## Goals / Non-Goals

**Goals:**
- Measure first: a baseline of the in-process executor at ~500k URLs, before any pool code.
- The same page preparation and extractor code runs in workers, unchanged, and behaves identically on every OS.
- Bounded memory, crash containment, and a clean shutdown.

**Non-Goals:**
- Parallel fetching, which is already asyncio.
- Tuning flags. The worker count is automatic in v0.1.

## Decisions

### D1. `spawn` on every OS, with `ProcessPoolExecutor`, behind `020`'s seam
- **The pool:** `concurrent.futures.ProcessPoolExecutor(max_workers=n, mp_context=get_context("spawn"), initializer=..., initargs=...)`, with `n = max(1, physical cores − 2)`, the verdict of the writer prototype of 2026-10-11 on the maintainer's laptop (8 physical cores, 6 workers). The re-run after `080` sweeps smaller counts and may lower the default (D6).
- **The pool executor** implements `020`'s `prepare(response)`: it submits the response to the pool and awaits the page-preparation record. The engine and the extractors do not change.
- **The initializer** runs once in each worker. It receives the settings snapshot and the registered extractors (pickled by reference), keeps them for the worker's life, and sets SIGINT to ignored (SIGBREAK too, on Windows). A work item is then only the fetched response, so the snapshot is pickled once per worker, never once per response.
  - Keeping them is the one piece of state of the worker module, set only by the initializer: the state is inherent to a pool whose initializer cannot return a value (ADR-0006, state only where inherent).
  - *Alternative:* `functools.partial(prepare, snapshot)` per submit. It pickles the snapshot, its compiled patterns and the extractor list with every response. Rejected.
- **Why `spawn` everywhere:** one start method means one behaviour to test. The cost is paid once per Crawl: about 1 second on Windows while workers import selectolax and the extractors, overlapped with robots.txt and the Seed request.
- *Alternative:* `forkserver` on POSIX. It is faster to start, but it behaves differently per OS. Rejected.
- *Alternative:* threads. selectolax releases the GIL only partly, and pure-Python extractors would still contend. Rejected.

### D2. The work item and the bounded queue
- **The work item:** the fetched response as page preparation takes it (URL, status, final headers, body bytes). The result is the page-preparation record, as the in-process executor returns it, which the engine hands to the per-response handlers in the crawl process.
- **Bounded queue:** the engine keeps a semaphore of `concurrency + 2 × n` permits. A permit is taken when a request for a followed URL starts, and given back when its record, or its non-HTML response, is submitted to the writer. Fetching therefore waits whenever page preparation falls behind. Where the permit sits in the engine is settled when `020`'s engine is built.

### D3. Crash containment
A worker that dies (a segfault in a native parser, or `os._exit`) breaks a `ProcessPoolExecutor` (`BrokenProcessPool`), which fails every pending future. The executor then:
1. creates a new pool, whose initializer gives each new worker the snapshot again
2. submits the failed work items again, **one at a time**
3. records the item that breaks the new pool again as `worker_crashed`, and resubmits the others normally

Each crash therefore costs one URL, plus a short serial phase.
- *Alternative:* recording every pending item as `worker_crashed`. That punishes innocent URLs. Rejected.

### D4. Shutdown
- **Normal end and stop:** on a normal end, and on a stop (an interrupt, or `060`'s stop request), the engine stops submitting and waits for the items in flight, as part of the grace period `020`'s `StopSignal` gives requests in flight. The executor then calls `shutdown(wait=True, cancel_futures=True)`. Workers ignore SIGINT, so a console Ctrl+C reaches only the crawl process, which shuts the pool down in order.
- **A second interrupt,** which calls `os._exit(130)` in `020`: the workers see their parent's pipe close and exit. The spec gives them 10 seconds.

### D5. Windows consoles
`multiprocessing` creates its children with no creation flags, so they attach to their parent's console, and a console-less parent is the only way to get new windows.
- **A console-less parent** is a DETACHED_PROCESS: each child would get a visible console window.
- `060` therefore uses CREATE_NO_WINDOW, whose hidden console the workers inherit.
- This change pins that behaviour with a Windows scenario, whose test starts the crawler under CREATE_NO_WINDOW itself.

### D6. The ~500k benchmark, first
- **The script:** `scripts/crawl_500k.py`, next to `scripts/writer_throughput.py`, generates a synthetic site of 500,000 linked pages from a template served by the fixture harness, and crawls it with no `--max-urls` limit.
- **A soak test too** (ROADMAP, Robustness rule): the site injects a share of the hostile fixtures' faults, and a run passes only if it ends with no crash, flat memory, and every URL accounted for in `urls`.
- **What it records:** URLs per second, peak memory of the crawl process and of each worker, machine-wide CPU and clock frequency, the crawl file's size with each table's share, the WAL peak, and the share of the crawl process's CPU time spent in page preparation.
- **Where it runs:** by hand, on a stated machine, never in CI or `scripts/check.py` (`docs/benchmarks.md`).
- **The runs:**
  - the baseline, against `020`'s in-process executor, before any pool code (task 1.2)
  - the crawl-file layout variants the store benchmark of 2026-10-10 left out (task 1.3, ROADMAP 026): the `links` layout, unless `030`'s task 10.1 has chosen it already, by 10.1's four layouts and decision rule, so that whichever runs first settles it once; a 16 KB page size; a zstd dictionary for stored HTML; and the WAL size of a ~100k-Page run without a concurrent reader
  - with the pool, next to the baseline (task 5.1)
  - **after `080`**, on the full v0.1 pipeline (ROADMAP, Build order), with the same script: it sweeps the worker count up to physical cores − 2 and keeps the count that gives the most Pages/s while the writer is never short of CPU; reports `response_headers`' share of the file, which over 10% limits that table to Internal URLs; and measures `040`'s live Issues during the Crawl (`040` D16: the full list under 30 s, `page <url>` under 1 s) and their effect on WAL checkpoints.
- **Results:** recorded in `docs/benchmarks.md`, with the machine and the commit, so later changes can compare.

### D7. The benchmark sizes the pool; it does not gate it
- The pool is built in groups 2–4 whatever the baseline shows (the user's decision of 2026-10-11). The baseline is the number the pool is compared with, and the re-run after `080` sizes it (D6).
- *Alternative:* the earlier draft's gate, building the pool only if the baseline showed page preparation as the bottleneck. Rejected by the user's decision: in the writer prototype, preparing one Page in the loop took about 26 ms, which alone caps a Crawl at a few dozen Pages per second, and the pool must land before the slice's end-to-end test.

## Test seams

The benchmark (group 1) is a script, not a test seam.

- **HTTP (local fixture site) (3) and seam 3+6:** the Crawl through the Crawl Service, with test extractors added to `default_hooks()` (`020` D9): one records its process id, one is slow, one ends its worker. They are module-level in a test module, which a `spawn` worker imports by name. The results are read from `urls`.
- **CLI (1), subprocess runs on each OS:**
  - the Windows `spawn` scenario
  - worker shutdown after completion and after SIGINT (CTRL_BREAK_EVENT to a new process group on Windows), with child processes listed through `psutil`
  - the Windows console scenario, under CREATE_NO_WINDOW, checked by listing visible top-level windows per process id
- **New seams or doubles:** none.

## Risks / Trade-offs

- [Pickling large bodies to workers costs CPU] → Bodies are bytes of up to 20 MiB (`022`'s cap), and pickling bytes is a memory copy. The settings snapshot is not pickled per response (D1). The benchmark measures the overhead.
- [A deterministic crash loop on one URL] → The retry happens once, alone, so a URL that always crashes is recorded after one extra attempt.
- [Worker start-up time on Windows] → It overlaps robots.txt and the Seed request, and is paid once per Crawl. A worker that needs the Public Suffix List loads it once, on its first lookup.
- [Too many workers for the writer] → Physical cores − 2 leaves two cores to the crawl process and the writer; the re-run after `080` lowers the default if fewer workers give more Pages/s. The queue bound follows the worker count, not the core count.

## Migration Plan

This change has no schema changes: `020` already lists the `parse_error` value `worker_crashed`.

## Open Questions

These are deferrable, and each is additive:
- A `--parse-workers <n>` flag for machines with many cores, or for constrained containers.
- Reusing one pool across several Crawls in a long-lived MCP server.
