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
- For **executor selection**, the Crawl Service defaults to in-process preparation and can opt into the pool. Changing the default is a separate step after native shutdown qualification and the in-process baseline (tasks 2.1a and 2.1b).

## Goals / Non-Goals

**Goals:**
- Measure the ~500k-URL baseline with the in-process executor before changing the default.
- The same page preparation and extractor code runs in workers, unchanged, and behaves identically on every OS.
- Bounded memory, crash containment, and a clean shutdown.

**Non-Goals:**
- Parallel fetching, which is already asyncio.
- Tuning flags. Automatic selection will choose a worker count when enabled.

## Decisions

### D1. Own `spawn` worker processes behind `020`'s seam
- **The workers** are `n` fresh interpreters that prepare one Page at a time, each with its own work and result channels. On POSIX the launcher uses the multiprocessing spawn protocol and sets the worker's process group at launch (D4). Windows uses a spawn launcher with explicit creation flags and handles (D5).
- The opt-in caller supplies **the worker count** the worker count within the platform's wait limits. For future automatic selection, `n = max(1, cores − 2)` within those limits, the verdict of the writer prototype of 2026-10-11 on the maintainer's laptop (8 physical cores, 6 workers). `cores` is `psutil.cpu_count(logical=False)`, or `os.cpu_count() // 2` when psutil cannot tell, capped by `os.process_cpu_count()` where Python has it (3.13 and later), so a container's CPU limit counts. `psutil` is a runtime dependency loaded by the pool, off the CLI startup path (`tests/cli/test_startup.py`). The re-run after `080` sweeps smaller counts and may lower the default (D6).
- **The pool executor** implements `020`'s `PageExecutor.prepare(url, response)`: it hands the URL and its response to an idle worker, or queues it until one is idle, and awaits the page-preparation record. One thread of the crawl process waits on every worker's pipe and process sentinel with `multiprocessing.connection.wait`, with a timeout at the nearest deadline (D8), and resolves the awaiting futures on the event loop. The engine and the extractors do not change.
- **The settings snapshot (`PageSettings`) and the registered extractors** (by reference) are the arguments a worker starts with, so they reach each worker once. A work item is then only the fetched response, so the snapshot is never pickled once per response. The worker's loop keeps them in local variables for its life, so the worker module holds no state. On POSIX the worker ignores SIGINT after startup; the separate process group already isolates it from keyboard interrupts at launch. Windows console isolation also starts at launch (D5).
  - *Alternative:* `functools.partial(prepare, snapshot)` per submit. It pickles the snapshot, its compiled patterns and the extractor list with every response. Rejected.
- **Why own workers rather than `concurrent.futures.ProcessPoolExecutor`:** the executor knows which worker holds which Page and since when, so it can end exactly the worker over its deadline (D8) and charge a crash to exactly one URL (D3).
  - *Alternative:* `ProcessPoolExecutor`, recreated after a crash or a deadline. It needs less code of ours, but it cannot end one worker (3.14's `kill_workers()` ends them all), so every timeout would end every worker and resubmit their Pages, paying about 1 second of `spawn` on Windows each time; it marks a future as running when the item enters its call queue, not when a worker takes it, so a deadline could not start at the take; and one dead worker fails every pending future, which needs a serial phase to find the culprit. Rejected: the code it saves moves into workarounds.
- All launchers use the same spawn protocol to load the worker and its snapshot. The cost is paid once per Crawl, and once per replaced worker: about 1 second on Windows while a worker imports selectolax and the extractors, overlapped at the start with robots.txt and the Seed request.
- *Alternative:* `forkserver` on POSIX. It is faster to start, but it behaves differently per OS. Rejected.
- *Alternative:* threads. selectolax releases the GIL only partly, and pure-Python extractors would still contend. Rejected.

### D2. The work item and the bounded queue
- **The work item:** the URL and its `FetchResult`, as `prepare_page` takes them. The result is the `PreparedPage`, as the in-process executor returns it, which the engine hands to the per-response handlers in the crawl process.
- **Bounded queue:** the engine keeps a semaphore of `cap + 2 × n` permits, where `cap` is `020`'s global request cap, `min(100, max(20, 4 × concurrency))`; With a preparation backlog, the dispatcher also bounds tasks per host at `concurrency + 2 × n`. The separate HTTP slots cap requests in flight, and return before preparation finishes. A URL task holds its room from dispatch until it submits its record or ends without one. When a host fills its window, URLs for other hosts in the current frontier batch can still start. Fetching therefore waits whenever page preparation falls behind.

### D3. Crash containment
A worker that dies (a segfault in a native parser, or `os._exit`) closes its pipe and signals its process sentinel. The executor then:
1. records the one Page that worker held as `worker_crashed`
2. starts a replacement worker with the same arguments
3. goes on; no other Page is touched, because each worker holds one Page at a time

Each crash therefore costs one URL and one worker start.
- *Alternative:* recording every Page in flight as `worker_crashed`, as a broken `ProcessPoolExecutor` would. That punishes innocent URLs. Rejected.

### D4. Shutdown
**In short:** The Crawl owner handles the stop and owns cleanup even during pool startup.

- On **completion**, the executor closes and reaps the workers, then joins the guardian. On a stop (the foreground interrupt or `060`'s Store request), the engine stops dispatch and gives Pages in flight the `020` grace period. Cancelling a Page in preparation ends its worker and leaves the unfinished URL `queued`. Close takes ownership of ongoing launches and replacements so that it can also end a child blocked in bootstrap.
- On a **second interrupt**, the owner calls `os._exit(130)`. The guardian watches the owner's process identity independently of the work channels and ends enrolled workers, including a worker busy in native code. The owner enrols a worker before releasing it to read work. A worker waiting for admission checks the owner's identity so an inherited work channel cannot leave it waiting indefinitely. The exit bound is 10 seconds after the owner exits.
- For **POSIX startup**, the launch places each worker in the guardian's group before entering the interpreter. The guardian can end a child in that group before enrolment, and a startup lease keeps it checking while a launch races owner exit. The executor checks actual child exit before reaping or replacing it because an inherited sentinel can remain open after exit.

### D5. Windows consoles
**In short:** The guardian, initial workers and replacements start outside the owner's console.

The launcher passes `CREATE_NO_WINDOW` at process creation. An attached foreground owner handles keyboard Ctrl+C and Ctrl+Break, and programmatic Ctrl+Break to its group or broadcast on its console. A broadcast reaches every group on that console, so a separate process group alone would leave children exposed during bootstrap. Starting outside the console protects them before Python can install any handler and avoids opening a window. The owner and guardian can then stop the children through D4.

The launcher gives each child an explicit list of bootstrap handles and standard streams. Redirected file and pipe streams remain usable. A console stream or missing handle uses the null device. A file holds the spawn payload, which can exceed a pipe buffer, and a separate ready pipe releases the child to read it. The launcher obtains the process handle at creation, and the spawn reducers duplicate work-channel handles into that process.

[`060` D4](../060-add-crawl-control/design.md#d4-windows-process-creation-approved) uses `CREATE_NO_WINDOW` for the background Crawl itself. The parse children use the same flag on their own launches in both foreground and background Crawls.

### D6. The ~500k benchmark, first
- **The script:** `scripts/crawl_500k.py`, next to `scripts/writer_throughput.py`, generates a synthetic site of 500,000 linked pages from a template served by the fixture harness, and crawls it with no `--max-urls` limit.
- **The site is seeded:** one seed gives the same pages, Links and faults on every run, and the script records how many Pages carry each injected fault and each Issue of `040`'s v0.1 Rules, so a run is checked by counts, not only timed. An option adds a response latency per request.
- **A direct mode** writes the same site into a crawl file through the store's units, with no HTTP, so `040`'s Rule queries and `050`'s `summary` can be measured on 500k URLs in minutes instead of hours.
- **A soak test too** (ROADMAP, Robustness rule): the site injects a share of the hostile fixtures' faults, including deeply nested `<div>` Pages over the deadline (D8) and Pages that end their worker, and a run passes only if it ends with no crash, flat memory, and every URL accounted for in `urls`.
- **What it records:** URLs per second, peak memory of the crawl process and of each worker, machine-wide CPU and clock frequency, the crawl file's size with each table's share, the WAL peak, and the share of the crawl process's CPU time spent in page preparation.
- **Where it runs:** by hand, on a stated machine, never in CI or `scripts/check.py` (`docs/benchmarks.md`).
- **The runs:**
  - the baseline, against `020`'s in-process executor, before any pool code (task 1.2); it leaves out the Pages over the deadline and those that end their worker, which the in-process executor cannot contain
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
- **The deadline:** `PREPARE_DEADLINE_SECONDS = 30`, a constant of `openlinx.crawl.pages.parse_pool`, with no flag, documented in `docs/architecture.md`. It runs from the moment a worker takes the Page, never from the time it waited in the queue, and it is real time measured by the executor's thread, not the context's `Clock`, because the work runs in another process. Thirty seconds is more than a thousand times a typical Page (about 26 ms in the writer prototype), lets 20,000 nested levels through, and stops 100,000. It is the same 30 seconds as the watchdog's margin over the Fetcher's deadline (`020` D16).
- **The watchdog:** it races the request only, which ends before page preparation starts, so the two never add up. If `020`'s engine ever awaits page preparation under the watchdog, its watchdog function must add this deadline.
- **Over the deadline:** the executor kills that one worker, records the URL with `parsed` = 0 and `parse_error` = `parse_timeout`, a value `020` lists (D18), and starts a replacement. The other workers and their Pages are not touched (D1).
- **The stop grace period** stays `020`'s 10 seconds: a stop ends a slow Page with its worker (D4) and does not wait for its deadline.
- *Alternative:* a regex pre-scan of the nesting depth in `020`, refusing a page above a limit before the parse. It covers one known shape only. Rejected by the user's decision.

## Test seams

The benchmark (group 1) is a script, not a test seam.

- **HTTP (local fixture site) (3) and seam 3+6:** the Crawl through the Crawl Service, with test extractors added to `default_hooks()` (`020` D9): one records its process id, one is slow, one never returns, one ends its worker. They are module-level in a test module, which a `spawn` worker imports by name. The results are read from `urls`. A test shortens the preparation deadline through the pool executor's parameter, whose default is the constant (D8).
- **CLI (1), subprocess runs on each OS:**
  - the Windows `spawn` scenario
  - worker shutdown after completion and interruption, using confirmed exit status and the committed Crawl state
  - Windows bootstrap shutdown with a private console, both group-targeted and broadcast Ctrl+Break at guardian, initial worker and replacement startup. Check console membership, raw process status, redirected streams, window visibility and the Store, including a subsequent Crawl. Use a matched no-signal run and negative controls for inherited console and missing early shutdown.
  - Windows foreground keyboard acceptance for Ctrl+C and Ctrl+Break during bootstrap and preparation, with the same stop, exit and Store checks
  - Windows owner death on a second Ctrl+Break while a child is still held in native bootstrap before admission. Check that every parse child exits within 10 seconds after owner exit and verify the committed Store state separately from the single-interrupt cases (task 4.2c).
  - Windows completion without visible windows, with the Seed and all 30 linked Pages in the Store
  - macOS and Linux native bootstrap shutdown after a single SIGINT and after owner exit on the second SIGINT, including a subsequent Crawl. See tasks 4.2 and 4.3 for the native matrix.
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
