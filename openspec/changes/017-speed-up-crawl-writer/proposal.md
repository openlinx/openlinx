## Why

The product bets on full crawls of large sites (ROADMAP, Positioning), and every Page a Crawl stores goes through `015`'s transactional writer. The store benchmark (2026-10-10) and the writer prototype (2026-10-11) measured that writer at realistic Link counts: about 466 Link rows per Page, navigation and footer included. As built, it stored 13.8 Pages/s writer-only at 20k Pages, against 17.2 for the prototype's writer. The measured costs are a savepoint per unit, SQLite's default page cache and temp store, and statements built again for every unit. Its API also has a gap that `020`'s hot path would inherit: `run()` reports a unit's success before the commit that makes it durable.

This change speeds up the writer and closes that gap before `020` writes through it, inside the store layer only. The writer stays a thread, `run()` and `run_async()` keep their meaning, and a new submit gives `020` an outcome at the commit, with backpressure.

## What Changes

> **Re-grounded (2026-10-11)** against the code of `015-add-crawl-store` as built on its branch (`src/spider/store/writer.py`, `src/spider/store/connections.py`, `tests/store/test_writer.py` and `tests/store/test_durability.py`), the archived `crawl-store` spec on that branch, the implementer's review of the prototype and the rulings of 2026-10-11, and the prototype's comparative runs. The writer process the prototype also built is not part of this change (design D1).

- **Submitting units:** `CrawlWriter.submit(unit)` returns a Future that is resolved at the commit that holds the unit, and fails with the unit's error or with the commit's error. `await CrawlWriter.submit_async(unit)` does the same from an event loop without blocking it. A window of 2,000 unresolved submitted units gives backpressure.
- **`run()` and `run_async()` are unchanged:** their result still means the unit ran, and `flush()` still means it is committed. Units stay `Callable[[Connection], T]`.
- **The optimistic batch:** the units of a batch run without a savepoint each. When one fails, the writer rolls the transaction back, runs the units before it again, and commits them at once: the replay commit, a new item in the spec's list of commits. The failing unit never runs again. Units may therefore run twice, and the spec now says that a unit has no effect outside the writer's connection, is deterministic and returns a value. A replay that does not reproduce the first run ends the writer.
- **Reads through the writer** run in its open transaction and commit nothing (a guard; `015` already behaves this way).
- **The writer's connection settings:** `temp_store=MEMORY`, a 64 MiB page cache and, in WAL mode, 256 MiB of memory-mapped I/O. There is no new setting. The killed-writer scenarios are proved again on Windows with memory mapping on, plus a new one: a new writer opens the file of a killed writer at once.
- **Prebuilt statements** become a documented rule for store modules: built once, and run with parameters.
- **A local throughput check:** `scripts/writer_throughput.py`, writer-only, 20k Pages at ~466 Link rows per Page. It must reach at least 12 Pages/s, with a WAL peak of at most 300 MB and a process RSS of at most 400 MB. It never runs in CI, and its links layout is provisional until the schema blueprint's lands.
- **Commands, flags, settings and MCP tools:** none added or changed. `[store]` keeps only `journal_mode`.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `crawl-store`:
  - **Transactional writer** (modified): reads through the writer commit nothing; a failing unit never runs again; units may run again before their commit; the replay commit joins the list of commits; what a result means; a half-way-failing unit after other units; a new writer opening a killed writer's file at once.
  - **Submitting units with their outcome at the commit** (added).
  - **The writer's connection settings** (added).

## Non-goals

- A writer in its own process, its pipes and its entry module: out of v0.1 (design D1). If one is ever added, it sits behind the same `submit()` and window, and its entry module gets a startup-allowlist-style import test (ROADMAP, 017's entry).
- Units as records with a registry: not needed while the writer is a thread (design D4). `020` D14's frozen row records stay `020`'s rule.
- The partial frontier index on `urls`, the per-URL unit and its fallback unit: `020-add-crawl-core` (v0.1), which owns `urls` (ROADMAP's re-grounding checklist).
- The parse pool and its size, and the end-to-end benchmark: `026-add-parse-pool` (v0.1).
- The `links` table and its layout: the schema blueprint, then `020` and `030-add-page-data` (v0.1).
- Pipes between a Crawl's processes, the writer claim and detached Crawls: `060-add-crawl-control` (v0.1).
- Connection settings for readers: unchanged, since readers open per operation. `050-add-query-and-segments` (v0.1) measures its own queries.

## Impact

- **Depends on:** `015-add-crawl-store` as built: `CrawlWriter` (`run`, `run_async`, `flush`, `close`, `on_commit`, `busy_seconds`, `CrawlWriterClosedError`), `spider.store.connections.opening` and its connect listeners, `StoreWorker`, `FakeClock`, and the `crawl-store` spec. PR #3 must be merged first, so that `openspec/specs/crawl-store` exists on `main`.
- **Used by:** `020` (`submit_async` for its per-URL unit, frontier reads as writer units, the prebuilt-statement rule); `030` and `040` (units that may run twice, prebuilt statements); `026` (the writer's share of CPU when it sizes the pool).
- **Code:** `src/spider/store/writer.py` and `src/spider/store/connections.py`; `scripts/writer_throughput.py`.
- **Tests:** `tests/store/test_writer.py` and `tests/store/test_durability.py`.
- **New dependencies:** `psutil` as a dev dependency, for the throughput check's RSS. It is not a runtime dependency, and `026` reuses it.
- **Docs:** `docs/crawl-store.md` ("Writing a Crawl"), `docs/architecture.md` (the store and its statement rule), and `docs/benchmarks.md` (a new "Writer capacity" section).
