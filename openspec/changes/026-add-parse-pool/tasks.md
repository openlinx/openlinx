> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

Seams (docs/testing.md):
- **[3+6]**: crawl the fixture site through the Crawl Service, with test extractors added to `020`'s `default_hooks()`, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Subprocess]**: seam 1, a real `spider` process

Group 1 is the benchmark, run against `020`'s in-process executor. Groups 2–4 build the pool, which is unconditional in v0.1 (the user's decision of 2026-10-11).

## 1. The 500k benchmark (baseline)

- [ ] 1.1 Benchmark: add `scripts/crawl_500k.py` with its synthetic 500,000-page fixture site, which injects a share of the hostile fixtures' faults (design D6). It records URLs per second, peak memory, machine-wide CPU and clock frequency, the crawl file's size with each table's share, the WAL peak, and the share of the crawl process's CPU time spent in page preparation, and it fails a run that crashes, grows its memory, or leaves a URL unaccounted for in `urls`. Check it on a 10,000-page run locally.
- [ ] 1.2 Docs: run the baseline against `020`'s in-process executor, and record its results, the machine and the commit in `docs/benchmarks.md`.
- [ ] 1.3 Check: the crawl-file layout variants (design D6). For the `links` layout, if `030`'s task 10.1 has already chosen it, record that choice; otherwise run 10.1's four layouts and decision rule, and record the choice in the "Links layout" section of `docs/benchmarks.md`, which 10.1 then takes. Also measure a 16 KB page size, a zstd dictionary for stored HTML, and the WAL size of a ~100k-Page run without a concurrent reader, and record them.
- [ ] 1.4 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Page preparation in worker processes

- [ ] 2.1 [3+6] Drive "Pages are parsed outside the crawl process".

  Done when: the pool executor in `spider.crawl.parse_pool` implements `020`'s `prepare(response)` with a `spawn` pool; its initializer gives each worker the settings snapshot and the registered extractors once, and a work item carries only the response (design D1); extractors and handlers are unchanged.
- [ ] 2.2 [CLI] Drive "The number of parse workers is reported": `parse_workers` in `crawl_started`, from the physical core count.
- [ ] 2.3 [Subprocess, Windows in CI] Drive "Pages are parsed in worker processes on Windows (Windows)".
- [ ] 2.4 Docs: document the parse pool (start method, worker count, the snapshot sent once through the initializer, the unchanged extractor interface) in `docs/architecture.md`.
- [ ] 2.5 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Bounded queue and crash containment

- [ ] 3.1 [3+6] Drive "Fetching waits for slow parsing": the permit semaphore of `concurrency + 2 × parse_workers`.
- [ ] 3.2 [3+6] Drive "A crashed worker is recorded": recreate the pool on `BrokenProcessPool`, resubmit one at a time, and record `worker_crashed`.
- [ ] 3.3 [3+6] Drive "The Crawl continues after a worker crash".
- [ ] 3.4 Docs: document the queue bound and crash handling in `docs/architecture.md`.
- [ ] 3.5 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Shutdown and Windows consoles

- [ ] 4.1 [Subprocess] Drive "No parse worker outlives a completed Crawl": `shutdown(wait=True, cancel_futures=True)`.
- [ ] 4.2 [Subprocess] Drive "An interrupt ends the parse workers": workers ignore SIGINT and SIGBREAK, and the pool shuts down within the grace period of `020`'s `StopSignal`.
- [ ] 4.3 [Subprocess, Windows in CI] Drive "Parse workers open no console window (Windows)".
- [ ] 4.4 Docs: document shutdown and Windows console behaviour (why `060` uses CREATE_NO_WINDOW) in `docs/architecture.md`.
- [ ] 4.5 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Change check

- [ ] 5.1 Rerun the benchmark with the pool, and record its results next to the baseline in `docs/benchmarks.md`.
- [ ] 5.2 Verify that every `#### Scenario:` in `specs/crawl-performance/spec.md` has exactly one test named after it.
- [ ] 5.3 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 5.4 Review: run the code-review skill on the whole change against `specs/crawl-performance/spec.md`, then refactor with the whole suite green.
