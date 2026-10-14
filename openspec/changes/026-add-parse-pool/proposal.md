## Why

`020-add-crawl-core` prepares each Page in the crawl process: it decodes, parses, runs the link extractor and the registered extractors, and normalises the discovered targets. At the scale target of about 500k URLs, that CPU work blocks the event loop (`030` adds many extractors), and the Crawl stalls while sockets sit idle. So page preparation runs in a process pool in v0.1, unconditionally (the user's decision of 2026-10-11): in the writer prototype of 2026-10-11, preparing one Page in the loop (about 474 Links resolved and normalised, plus the parse) took about 26 ms, which alone caps a Crawl at a few dozen Pages per second, whatever the writer does. `020` already calls page preparation through an executor seam, so the pool plugs in without changing the engine or the extractors. This change also makes the pool safe:
- memory stays bounded when page preparation falls behind
- a crashing worker costs one URL, not the Crawl
- a Page that takes too long to prepare, such as deeply nested HTML, costs one URL and one worker, not the Crawl
- workers never outlive their Crawl
- no console windows appear on Windows

## What Changes

- **The ~500k-URL benchmark comes first:** a script and a synthetic fixture site, run by hand on a stated machine and never in CI. Its first run is the baseline, against `020`'s in-process executor. It is also the soak test of the robustness rule: the site injects a share of the hostile fixtures' faults. Its results are recorded in `docs/benchmarks.md`.
- **Page preparation moves into `spawn` worker processes of our own** behind `020`'s executor seam, one Page per worker at a time, with one worker per physical core minus 2, at least 1, on every OS. `020`'s extractors run unchanged in the workers; the per-response handlers stay in the crawl process and get the records back.
- **The settings snapshot reaches each worker once,** as an argument the worker starts with, together with the registered extractors. A work item carries only the fetched response.
- **`crawl_started` event:** its `parse_workers`, which `020` reports as 0, becomes the pool's size.
- **A bounded queue:** when page preparation falls behind, fetching waits. At most `020`'s global request cap + 2 × `parse_workers` Pages are requested but not yet prepared (`--concurrency` + 2 × `parse_workers` on one host).
- **A crashed worker is replaced.** The URL it was preparing gets `parse_error` = `worker_crashed`, a value `020` already lists, and the Crawl goes on.
- **A deadline of 30 seconds per Page,** from the moment a worker takes it: a worker over it is killed and replaced, the URL gets `parse_error` = `parse_timeout`, a value `020` lists, and no other Page is charged. It is a constant, with no flag (the user's decision of 2026-10-14, over a depth pre-scan in `020`).
- **Workers end with their Crawl,** after a normal end, a stop or an interrupt.
- **Windows:** workers inherit their parent's console, so a Crawl started without a visible console, such as `060`'s CREATE_NO_WINDOW background process, opens no windows.
- **The benchmark is run again** with the pool, and its results are recorded next to the baseline. The re-run on the full v0.1 pipeline after `080` (ROADMAP, Build order) uses the same script to size the pool.
- **Flags:** none new. **MCP tools:** none.

## Capabilities

### New Capabilities
- `crawl-performance`: covers page preparation in worker processes and the reported worker count, the bounded queue, worker crash recovery, the preparation deadline, worker shutdown, and console behaviour on Windows.

### Modified Capabilities
- None. `020-add-crawl-core`'s `crawling` capability is not archived yet. This change reports the pool's size in `020`'s `crawl_started` `parse_workers` and writes the `parse_error` values `worker_crashed` and `parse_timeout`, which `020` lists already.

## Non-goals

- A `--parse-workers` flag: see design.md, Open Questions.
- JavaScript rendering: **v1.1**.
- Distributed Crawls: **backlog**.

## Impact

- **Depends on:**
  - `020-add-crawl-core`: page preparation, its settings snapshot and the executor seam of the `CrawlContext` (D9, D15), the `Hooks` with their extractors and per-response handlers, `PageInput` and `DiscoveredLink`, `parse_error`, the engine and its `StopSignal` with the grace period, and the events.
  - `000-scaffold-project`: CI on three OSes and the fixture site.
- **Used by:**
  - `030-add-page-data`, whose Page extractor runs in the pool, and whose `links` layout this change's benchmark may settle (ROADMAP, 026).
  - `040-add-rules`, whose live Issues latency the 500k run measures (`040` D16).
  - `060-add-crawl-control`, whose background process uses CREATE_NO_WINDOW so the workers inherit a hidden console.
- **Code:** `scripts/crawl_500k.py` and its synthetic site, and `spider.crawl.parse_pool` with the pool executor and its workers behind `020`'s seam.
- **New dependencies:** `psutil` becomes a runtime dependency (it is a test dependency today), to count physical cores; `spider.crawl.parse_pool` imports it, never the startup path.
- **Docs:** the benchmark results in `docs/benchmarks.md`, and the parse pool in `docs/architecture.md`.
