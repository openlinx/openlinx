## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** runs extractors in the crawl process through the extractor registry.
  - Extractors are functions over a parsed tree that return msgspec structs. Sinks turn those structs into rows inside the URL's writer unit.
  - Test extractors can be registered through the public registry.
- **Platforms:** Windows only has `spawn`. Python 3.14 changes the default start method on Linux to `forkserver`. `fork` in a process with threads is unsafe on macOS.
- **`060-add-crawl-control`** starts background Crawls with CREATE_NO_WINDOW, which is approved.
- **The pool is conditional:** it is built only if the benchmark (D6) shows that parsing is the bottleneck. D1–D5 apply only if it goes ahead (D7).

## Goals / Non-Goals

**Goals:**
- Measure first: a baseline of in-process parsing at ~500k URLs, before any pool code.
- The same extractor code runs in workers, unchanged, and behaves identically on every OS.
- Bounded memory, crash containment, and a clean shutdown.

**Non-Goals:**
- Parallel fetching, which is already asyncio.
- Tuning flags. The worker count is automatic in v0.1.

## Decisions

### D1. `spawn` on every OS, with `ProcessPoolExecutor`
- **The pool:** `concurrent.futures.ProcessPoolExecutor(max_workers=n, mp_context=get_context("spawn"))`, with `n = min(8, max(1, os.cpu_count() - 1))`.
- **Why `spawn` everywhere:** one start method means one behaviour to test. The cost is paid once per Crawl: about 1 second on Windows while workers import selectolax and the extractors, overlapped with robots.txt and the Seed request.
- **The initializer:** imports the extractor registry, and sets SIGINT to ignored (SIGBREAK too, on Windows).
- *Alternative:* `forkserver` on POSIX. It is faster to start, but it behaves differently per OS. Rejected.
- *Alternative:* threads. selectolax releases the GIL only partly, and pure-Python extractors would still contend. Rejected.

### D2. The work item and the bounded queue
- **The work item:** (URL id, URL, final headers, decoded body bytes, charset hint, the robots token). The result is the dict of extractor structs, or an error.
- **Bounded queue:** the engine keeps a semaphore of `concurrency + 2 × n` permits. A permit is taken when a request for a followed URL starts, and given back when its parse result, or its non-HTML response, reaches the writer. Fetching therefore waits whenever parsing falls behind.

### D3. Crash containment
A worker that dies (a segfault in a native parser, or `os._exit`) breaks a `ProcessPoolExecutor` (`BrokenProcessPool`), which fails every pending future. The engine then:
1. creates a new pool
2. submits the failed work items again, **one at a time**
3. records the item that breaks the new pool again as `worker_crashed`, and resubmits the others normally

Each crash therefore costs one URL, plus a short serial phase.
- *Alternative:* recording every pending item as `worker_crashed`. That punishes innocent URLs. Rejected.

### D4. Shutdown
- **Normal end and stop:** on a normal end, and on a stop (an interrupt, or `060`'s stop request), the engine stops submitting and waits for the items in flight, as part of the grace period `020` gives requests in flight. It then calls `shutdown(wait=True, cancel_futures=True)`. Workers ignore SIGINT, so a console Ctrl+C reaches only the crawl process, which shuts the pool down in order.
- **A second interrupt,** which calls `os._exit(130)` in `020`: the workers see their parent's pipe close and exit. The spec gives them 10 seconds.

### D5. Windows consoles
`multiprocessing` creates its children with no creation flags, so they attach to their parent's console, and a console-less parent is the only way to get new windows.
- **A console-less parent** is a DETACHED_PROCESS: each child would get a visible console window.
- `060` therefore uses CREATE_NO_WINDOW, whose hidden console the workers inherit.
- This change pins that behaviour with a Windows scenario, whose test starts the crawler under CREATE_NO_WINDOW itself.

### D6. The ~500k benchmark, first
- **The benchmark:** `benchmarks/crawl_500k.py` generates a synthetic site of 500,000 linked pages (template HTML, about 30 Links each) served by the fixture harness. It crawls the site with `--max-urls 0`, and records URLs per second, peak memory of the crawl process and of any workers, the crawl file's size, and the share of the crawl process's CPU time spent parsing and extracting.
- **The baseline:** its first run is against `020`'s in-process parsing, with no pool (task 1.1). If the pool goes ahead, it runs again with the pool (task 5.1).
- **When it runs:** manually, and in a nightly CI workflow on Linux. It is never part of the pull-request gate.
- **Results:** recorded in `docs/benchmarks.md`, with the machine type and the commit, so later changes (`030`'s Link rows) can compare.

### D7. The benchmark gates the pool
- **The gate:** after group 1, the maintainer reads the baseline in `docs/benchmarks.md` and decides whether the pool goes ahead (task 1.5). Implementation stops until they decide.
- **Yes:** parsing is the bottleneck. Groups 2–4 implement D1–D5.
- **No:** groups 2–4 are not implemented. The spec and the pool tasks are descoped, and the change is archived with only the benchmark.
- **The decision** is recorded in `docs/benchmarks.md`, next to the numbers it rests on.
- *Alternative:* building the pool on the design's estimate alone. It adds processes, pickling and crash handling that may buy nothing. Rejected.

## Test seams

These apply to groups 2–4, if the pool goes ahead. The benchmark (group 1) is a script, not a test seam.

- **HTTP (local fixture site) (3) and seam 3+6:** the Crawl, with test extractors registered through `020`'s public registry: one records its process id, one is slow, one ends its worker. The results are read from `urls`.
- **CLI (1), subprocess runs on each OS:**
  - the Windows `spawn` scenario
  - worker shutdown after completion and after SIGINT (CTRL_BREAK_EVENT to a new process group on Windows), with child processes listed through `psutil`
  - the Windows console scenario, under CREATE_NO_WINDOW, checked by listing visible top-level windows per process id
- **New seams or doubles:** none.

## Risks / Trade-offs

- [Pickling large bodies to workers costs CPU] → Bodies are bytes of up to 20 MiB (`022`'s cap), and pickling bytes is a memory copy. The benchmark measures the overhead.
- [A deterministic crash loop on one URL] → The retry happens once, alone, so a URL that always crashes is recorded after one extra attempt.
- [Worker start-up time on Windows] → It overlaps robots.txt and the Seed request, and is paid once per Crawl.
- [Too many workers on small machines with a large `--concurrency`] → The worker count is capped at 8. The queue bound follows the worker count, not the core count.

## Migration Plan

This change has no schema changes beyond the `parse_error` value `worker_crashed`, which is free text.

## Open Questions

These are deferrable, and each is additive:
- A `--parse-workers <n>` flag for machines with many cores, or for constrained containers.
- Reusing one pool across several Crawls in a long-lived MCP server.
