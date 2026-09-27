## Why

`020-add-crawl-core` parses HTML in the crawl process. That is fine for small sites, but at the scale target of about 500k URLs, parsing and extraction (`030` adds many extractors) would block the event loop, and the Crawl would stall on CPU work while sockets sit idle. The approved design runs parsing in a process pool. This change moves the existing extractors into worker processes without changing their interface, and makes the pool safe:
- memory stays bounded when parsing falls behind
- a crashing worker costs one URL, not the Crawl
- workers never outlive their Crawl
- no console windows appear on Windows

## What Changes

- **Parsing moves into a `spawn` process pool** with `min(8, max(1, CPU count − 1))` workers, on every OS. The extractors and sinks of `020` (and later `030`) run unchanged in the workers.
- **`crawl_started` event:** its `data` gains `parse_workers`.
- **A bounded parse queue:** when parsing falls behind, fetching waits. At most `--concurrency` + 2 × `parse_workers` Pages are requested but not yet parsed.
- **A crashed worker is replaced.** The URL it was parsing gets `parse_error` = `worker_crashed`, and the Crawl goes on.
- **Workers end with their Crawl,** after a normal end or an interrupt.
- **Windows:** workers inherit their parent's console, so a Crawl started without a visible console, such as `060`'s CREATE_NO_WINDOW background process, opens no windows.
- **The ~500k-URL benchmark:** a script and a synthetic fixture site, run manually or nightly and not part of the CI gate. Its results are recorded in the docs.
- **Flags:** none new. **MCP tools:** none.

## Capabilities

### New Capabilities
- `crawl-performance`: covers parsing in worker processes and the reported worker count, the bounded parse queue, worker crash recovery, worker shutdown, and console behaviour on Windows.

### Modified Capabilities
- None. There are no main specs yet. This change adds `parse_workers` to the `crawl_started` event of `020-add-crawl-core` and the `parse_error` value `worker_crashed`.

## Non-goals

- A `--parse-workers` flag: see design.md, Open Questions.
- JavaScript rendering: **v1.1**.
- Distributed Crawls: **backlog**.

## Impact

- **Depends on:**
  - `020-add-crawl-core`: the extractor and sink registries, `parse_error`, the engine and its stop flag, the events, and the test extractors registered through the public registry.
  - `000-scaffold-project`: CI on three OSes and the fixture site.
- **Used by:**
  - `030-add-page-data`, whose extractors run in the pool.
  - `060-add-crawl-control`, whose background process uses CREATE_NO_WINDOW so the workers inherit a hidden console.
- **Code:** `src/spider/crawl/parse_pool.py`, the engine's dispatch to it, and `benchmarks/`.
- **New dependencies:** none at runtime. `psutil`, already a dependency of `015`, is used by tests to list child processes.
- **Docs:** the parse pool in `docs/architecture.md`, and the benchmark results in `docs/benchmarks.md`.
