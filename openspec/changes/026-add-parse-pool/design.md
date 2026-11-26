> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** (its groups 4 and later, page preparation and the executor seam among them, are not coded yet; this draft follows its design):
  - **Page preparation** (`020` D9) is `prepare_page(url, response, settings)` in `openlinx.crawl.pages`, one pure, module-level function of a URL, its `FetchResult` and the settings snapshot, `PageSettings`, that its worker received once at start (the robots token, `--strip-params`, the `ScopeRules`, and the settings that registered extractors read, such as `030`'s `content_area`). It decodes, parses once, runs the link extractor, the registered extractors and the robots directives parser, and returns one frozen msgspec record, `PreparedPage`. `PageInput` sits beside it in `openlinx.crawl.pages`.
  - **The executor seam:** the engine calls `await executor.prepare(url, response)` on the `PageExecutor` of the `CrawlContext` (`020` D15), a Protocol in `openlinx.crawl.pages`, where `020`'s `InProcessExecutor` calls `prepare_page` on the loop's thread. `020` ships the in-process executor; this change plugs a process pool in behind the same seam without touching the engine.
  - **`Hooks`** (`020` D9) is a frozen dataclass of tuples in the `CrawlContext`: extractors, per-response handlers and post-crawl passes, listed by `default_hooks()`. Extractors are module-level functions from the parsed tree and a `PageInput` to a msgspec struct, so a worker process imports them by name. Per-response handlers turn a `UrlResult` into store rows; they run in the crawl process for every URL that reaches a final state, so they stay there. A test adds its own extractors and handlers to `default_hooks()` and passes them to the Crawl Service.
  - **The link extractor** returns `DiscoveredLink` values with a non-nullable normalised target (a malformed reference is dropped) and an `ordinal`, the Link's place in document order. It takes an `is_internal: Callable[[NormalizedUrl], bool]` and imports nothing of the Scope; page preparation passes the one built from the snapshot's `ScopeRules`.
  - **`ScopeRules`** holds strings only and pickles to about 134 bytes. The Public Suffix List behind `subdomains` is loaded lazily, once per process, on the first lookup (about 56 ms), so each worker that needs it loads it once.
  - **`parse_error`** already lists `worker_crashed` and `parse_timeout` for this change (`020` D18). Both keep `parsed` = 0, because nothing came out of the worker; a registered extractor that raises inside page preparation is not a crash, and `020` records it as `parsed` = 1 with `extractor_error`, following the Page's Links (the user's decision of 2026-10-14), and the `StopSignal` gives requests in flight a grace period of 10 seconds.
- **ADR-0006:** page preparation's per-response records, which cross the pool (`DiscoveredLink`, extractor outputs, the page-preparation record) or are built beside them in the worker (`PageInput`), are frozen `msgspec.Struct`s. They cross the process boundary as they are, and pickle about twice as fast as slotted dataclasses.
- **Platforms:** Windows only has `spawn`. Python 3.14 changes the default start method on Linux to `forkserver`. `fork` in a process with threads is unsafe on macOS.
- **`060-add-crawl-control`** starts background Crawls with CREATE_NO_WINDOW, which is approved.
- **The pool is unconditional in v0.1** (the user's decision of 2026-10-11). The benchmark measures and sizes it; it does not decide whether it is built.

## Goals / Non-Goals

**Goals:**
- Measure first: a baseline of the in-process executor at ~500k URLs before selecting the pool by default.
- The same page preparation and extractor code runs in workers, unchanged, and behaves identically on every OS.
- Bounded memory, crash containment, and a clean shutdown.

**Non-Goals:**
- Parallel fetching, which is already asyncio.
- Tuning flags. The worker count is automatic in v0.1.

## Decisions

### D1. Own `spawn` worker processes behind `020`'s seam
- **The workers:** `n` processes started with `multiprocessing.get_context("spawn")`, each with its own work socket and result pipe, that prepare one Page at a time.
- **Their number:** `n = max(1, cores − 2)`, the verdict of the writer prototype of 2026-10-11 on the maintainer's laptop (8 physical cores, 6 workers). `cores` is `psutil.cpu_count(logical=False)`, or `os.cpu_count() // 2` when psutil cannot tell, capped by `os.process_cpu_count()` where Python has it (3.13 and later), so a container's CPU limit counts. `psutil` is a runtime dependency imported inside the Page preparation pool and its guardian, off the CLI help path (`tests/cli/test_startup.py`). The re-run after `080` sweeps smaller counts and may lower the default (D6).
- **The pool executor** lives in the page preparation layer (`openlinx.crawl.pages.parse_pool`)
  and implements `020`'s `PageExecutor.prepare(url, response)`. It hands the URL and its
  response to an idle worker, or queues it until one is idle, and awaits the prepared Page.
  The event loop can cancel a blocked work transfer without waiting for the worker to read.
  One thread waits for worker results using `multiprocessing.connection.wait` and hands them
  to the event loop, which tracks preparation and readiness deadlines through the real Clock.
  The engine and the extractors do not change.
- **The settings snapshot (`PageSettings`) and the registered extractors** (by reference) are the arguments a worker starts with, so they reach each worker once. A work item is then only the fetched response, so the snapshot is never pickled once per response. The worker's loop keeps them in local variables for its life, so the worker module holds no state. On POSIX, each worker ignores SIGINT when its target starts. Windows children are isolated at creation (D5).
  - *Alternative:* `functools.partial(prepare, snapshot)` per submit. It pickles the snapshot, its compiled patterns and the extractor list with every response. Rejected.
- **Why own workers rather than `concurrent.futures.ProcessPoolExecutor`:** the executor knows which worker holds which Page and since when, so it can end exactly the worker over its deadline (D8) and charge a crash to exactly one URL (D3).
  - *Alternative:* `ProcessPoolExecutor`, recreated after a crash or a deadline. It needs less code of ours, but it cannot end one worker (3.14's `kill_workers()` ends them all), so every timeout would end every worker and resubmit their Pages, paying about 1 second of `spawn` on Windows each time; it marks a future as running when the item enters its call queue, not when a worker takes it, so a deadline could not start at the take; and one dead worker fails every pending future, which needs a serial phase to find the culprit. Rejected: the code it saves moves into workarounds.
- **Why `spawn` everywhere:** one start method means one behaviour to test. The cost is paid once per Crawl, and once per replaced worker: about 1 second on Windows while a worker imports selectolax and the extractors, overlapped at the start with robots.txt and the Seed request.
- *Alternative:* `forkserver` on POSIX. It is faster to start, but it behaves differently per OS. Rejected.
- *Alternative:* threads. selectolax releases the GIL only partly, and pure-Python extractors would still contend. Rejected.

### D2. The work item and the bounded queue
- **The work item:** the URL and its `FetchResult`, as `prepare_page` takes them. The result is the `PreparedPage`, as the in-process executor returns it, which the engine hands to the per-response handlers in the crawl process.
- **Bounded queue:** the engine keeps a semaphore of `cap + 2 × n` permits, where `cap` is `020`'s global request cap, `min(100, max(20, 4 × concurrency))`; `--concurrency` itself is a per-host limit, so on one host it bounds the requests first. A permit is taken when a request for a followed URL starts, and given back when its record, or its non-HTML response, is submitted to the writer. Fetching therefore waits whenever page preparation falls behind. Where the permit sits in the engine is settled when `020`'s engine is built.

### D3. Crash containment
A worker that dies (a segfault in a native parser, or `os._exit`) closes its pipe and signals its process sentinel. The executor then:
1. records the one Page that worker held as `worker_crashed`
2. starts a replacement worker with the same arguments
3. goes on; no other Page is touched, because each worker holds one Page at a time

Each crash therefore costs one URL and one worker start.
- *Alternative:* recording every Page in flight as `worker_crashed`, as a broken `ProcessPoolExecutor` would. That punishes innocent URLs. Rejected.

### D4. Shutdown
- **Normal end and stop:** on a normal end, and on a stop (an interrupt, or `060`'s stop request), the engine stops submitting and waits for the Pages in flight, as part of the grace period `020`'s `StopSignal` gives requests in flight. The executor then sends each worker a stop message and joins it. A worker still preparing a Page when the grace period ends is killed, and that URL stays `queued`, as `020` leaves a request cancelled before its submit. Workers ignore SIGINT, so a console Ctrl+C reaches only the crawl process, which ends the workers in order.
- **A second interrupt** calls `os._exit(130)` in `020`. A separate guardian checks the
  Crawl's OS process identity independently of the work channels. It ends its enrolled
  workers even while native preparation holds a worker's GIL. The Crawl waits for enrolment
  before sending an admission byte and the settings snapshot. A worker waiting for that byte
  also checks the Crawl's identity so it can exit before enrolment, even if a different process
  inherited the work channel. The spec gives workers 10 seconds after the Crawl exits.
- **POSIX startup:** the OS places each worker in the guardian's process group before running
  the interpreter. The guardian can end a worker in that group before it has received the PID.
  An inherited startup pipe keeps the guardian checking the group while a launch coincides
  with owner death. A temporary file carries the spawn preparation data so the Crawl can
  finish the launch even when the worker stalls before reading it.
- **Orderly close:** close takes ownership of ongoing starts and replacements, closes the
  work sockets after the engine's grace period, and ends any remaining workers within a
  shared grace and reap budget. A worker that still holds cancelled work, or is unready when
  the engine has cancelled a call waiting for a start or a worker, is killed immediately.
  The guardian is joined once the workers have been reaped. The executor also reaps an ended
  worker before launching its replacement. On POSIX a sentinel can close before the OS
  reports exit or stay open after exit when another process has inherited its writer.

### D5. Windows consoles
**In short:** The Windows guardian, workers and replacements start outside the Crawl's
console, with no visible console window.

Each child starts with `CREATE_NO_WINDOW`. A Ctrl+Break broadcast goes to every
process group on the sender's console, so creation in a separate process group
alone would protect only against an event addressed to the owner's group.
`CREATE_NEW_CONSOLE` would allocate a separate console but could show a window.
Each child keeps the console isolation it had at creation throughout bootstrap.

The spawn launcher passes redirected file and pipe handles explicitly. If a
standard stream points to the owner's console or has no handle, the launcher
uses the null device for that stream. It inherits only those streams and the
bootstrap handles. A temporary file carries the spawn payload, which may be
larger than a pipe buffer. The owner publishes the file with a byte on a separate
pipe, so it can finish tracking a child before that child's interpreter reads
the payload. The usual spawn reducers still duplicate the work-channel handles.

[`060` D4](../060-add-crawl-control/design.md#d4-windows-process-creation-approved)
also uses `CREATE_NO_WINDOW` for the background Crawl itself.

### D6. The ~500k benchmark, first
- **The script:** `scripts/crawl_500k.py`, next to `scripts/writer_throughput.py`, generates a synthetic site of 500,000 linked pages from a template served by the fixture harness, and crawls it with no `--max-urls` limit.
- **The site is seeded:** one seed gives the same pages, Links and faults on every run, and the script records how many Pages carry each injected fault and each Issue of `040`'s v0.1 Rules, so a run is checked by counts, not only timed. An option adds a response latency per request.
- **A direct mode** writes the same site into a crawl file through the store's units, with no HTTP, so `040`'s Rule queries and `050`'s `summary` can be measured on 500k URLs in minutes instead of hours.
- **A soak test too** (ROADMAP, Robustness rule): the site injects a share of the hostile fixtures' faults, including deeply nested `<div>` Pages over the deadline (D8) and Pages that end their worker, and a run passes only if it ends with no crash, flat memory, and every URL accounted for in `urls`.
- **What it records:** URLs per second, peak memory of the crawl process and of each worker, machine-wide CPU and clock frequency, the crawl file's size with each table's share, the WAL peak, and the share of the crawl process's CPU time spent in page preparation.
- **Where it runs:** by hand, on a stated machine, never in CI or `scripts/check.py` (`docs/benchmarks.md`).
- **The runs:**
  - the baseline, against `020`'s in-process executor, before switching the default (task 1.2); it leaves out the Pages over the deadline and those that end their worker, which the in-process executor cannot contain
  - the crawl-file layout variants the store benchmark of 2026-10-10 left out (task 1.3, ROADMAP 026): the `links` layout, unless `030`'s task 10.1 has chosen it already, by 10.1's four layouts and decision rule, so that whichever runs first settles it once; a 16 KB page size; a zstd dictionary for stored HTML; and the WAL size of a ~100k-Page run without a concurrent reader
  - with the pool, next to the baseline (task 5.1), with these variants, each against the same run without it (decided 2026-10-14: measured here, not built in `020`):
    - a bounded `url` → id LRU cache in the writer (for example 50,000 entries, cleared when a batch rolls back), which skips the `urls_url` lookup for the navigation and footer Links every Page repeats. If it wins, `030`'s group 10 builds it, sharing the writer's rollback hook of `030`'s task 10.2 (ruled 2026-10-14)
    - in the link extractor: a cheap `//` check before `urlsplit`, skipping `urljoin` for an absolute reference already in `020`'s `NORMAL_FORM`, and `gc=False` on `DiscoveredLink`
  - **after `080`**, on the full v0.1 pipeline (ROADMAP, Build order), with the same script: it sweeps the worker count up to physical cores − 2 and keeps the count that gives the most Pages/s while the writer is never short of CPU; reports `response_headers`' share of the file, which over 10% limits that table to Internal URLs; and measures `040`'s live Issues during the Crawl (`040` D16: the full list under 30 s, `page <url>` under 1 s) and their effect on WAL checkpoints.
- **Method:** runs of variants are interleaved and the minimum is kept, each stage starts from a fresh crawl file, counts are preferred to wall time, and the rows of retracted runs stay in `docs/benchmarks.md`. The maintainer's laptop varies by up to half between runs made at different times, and its absolute numbers by about six times with its CPU state, so the script records and pins that state (power plan, clock frequency) for every run.
- **Results:** recorded in `docs/benchmarks.md`, with the machine and the commit, so later changes can compare.

### D7. The benchmark sizes the pool; it does not gate it
- The pool is built in groups 2–4 whatever the baseline shows (the user's decision of 2026-10-11). The baseline is the number the pool is compared with, and the re-run after `080` sizes it (D6).
- *Alternative:* the earlier draft's gate, building the pool only if the baseline showed page preparation as the bottleneck. Rejected by the user's decision: in the writer prototype, preparing one Page in the loop took about 26 ms, which alone caps a Crawl at a few dozen Pages per second, and the pool must land before the slice's end-to-end test.

### D8. A deadline for preparing one Page
- **Why:** lexbor parses deeply nested `<div>` elements super-linearly: 20,000 levels take 0.44 s, 100,000 levels about 80 s of CPU for a 1.1 MB page, while `<span>`, `<p>` and `<li>` stay linear (measured during `020`'s group 3, 2026-10-14). One hostile Page would hold a worker for minutes. The user chose this generic deadline over a depth pre-scan in `020` (2026-10-14), because it also covers any other slow input.
- **The deadline:** `PREPARE_DEADLINE_SECONDS = 30`, a constant of `openlinx.crawl.pages.parse_pool`, with no flag, documented in `docs/architecture.md`. It runs when a worker acknowledges taking the Page and uses the real Clock because the work runs in another process. A ready worker that cannot take its dispatched Page within a separate delivery deadline is ended and recorded as `worker_crashed`. Time waiting in the pool queue is outside both deadlines. Thirty seconds is more than a thousand times a typical Page (about 26 ms in the writer prototype), lets 20,000 nested levels through, and stops 100,000. It is the same 30 seconds as the watchdog's margin over the Fetcher's deadline (`020` D16).
- **The watchdog:** it races the request only, which ends before page preparation starts, so the two never add up. If `020`'s engine ever awaits page preparation under the watchdog, its watchdog function must add this deadline.
- **Over the deadline:** the executor kills that one worker, records the URL with `parsed` = 0 and `parse_error` = `parse_timeout`, a value `020` lists (D18), and starts a replacement. The other workers and their Pages are not touched (D1).
- **The stop grace period** stays `020`'s 10 seconds: a stop ends a slow Page with its worker (D4) and does not wait for its deadline.
- *Alternative:* a regex pre-scan of the nesting depth in `020`, refusing a page above a limit before the parse. It covers one known shape only. Rejected by the user's decision.

## Test seams

The benchmark (group 1) is a script, not a test seam.

- **HTTP (local fixture site) (3) and seam 3+6:** the Crawl through the Crawl Service, with test extractors added to `default_hooks()` (`020` D9): one records its process id, one is slow, one never returns, one ends its worker. They are module-level in a test module, which a `spawn` worker imports by name. The results are read from `urls`. A test shortens the preparation deadline through the pool executor's parameter, whose default is the constant (D8).
- **Crawl Service's executor extension (2):** call the public `PageExecutor` lifecycle with
  real workers to exercise readiness, cancellation and process exit. A test controls the
  snapshot or extractor to observe the relevant worker before blocking it.
- **CLI (1), subprocess runs on each OS:**
  - the Windows `spawn` scenario
  - worker shutdown after completion and after SIGINT (CTRL_BREAK_EVENT to a new process group on Windows), with child processes listed through `psutil`
  - the Windows console scenario, under CREATE_NO_WINDOW, checked by listing visible top-level windows per process id
- **New seams or doubles:** none.

## Risks / Trade-offs

- [Pickling large bodies to workers costs CPU] → Bodies are bytes of up to 20 MiB (`022`'s cap), and pickling bytes is a memory copy. The settings snapshot is not pickled per response (D1). The benchmark measures the overhead.
- [Worker replacements on a hostile site] → Each crash or timeout costs one worker start, about 1 second on Windows, during which the other workers go on. The benchmark's hostile share includes crashing and deeply nested Pages, so it measures the cost.
- [Worker start-up time on Windows] → It overlaps robots.txt and the Seed request, and is paid once per Crawl. A worker that needs the Public Suffix List loads it once, on its first lookup.
- [Too many workers for the writer] → Physical cores − 2 leaves two cores to the crawl process and the writer; the re-run after `080` lowers the default if fewer workers give more Pages/s. The queue bound follows the worker count, not the core count.

## Migration Plan

This change has no schema changes: `020` already lists the `parse_error` values `worker_crashed` and `parse_timeout`.

## Open Questions

These are deferrable, and each is additive:
- A `--parse-workers <n>` flag for machines with many cores, or for constrained containers.
- Reusing one pool across several Crawls in a long-lived MCP server.
