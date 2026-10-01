Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

Seams (docs/testing.md):
- **[3+6]**: crawl the fixture site, with test extractors registered through `020`'s public registry, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Subprocess]**: seam 1, a real `spider` process

Group 1 is the benchmark, run against `020`'s in-process parsing. Groups 2–4 build the pool, and start only after the decision in task 1.5.

## 1. The 500k benchmark (baseline)

- [ ] 1.1 Benchmark: add `benchmarks/crawl_500k.py` with its synthetic 500,000-page fixture site. It measures URLs per second, peak memory, crawl file size, and the share of the crawl process's CPU time spent parsing and extracting. It runs against `020`'s in-process parsing, with no pool. Check it on a 10,000-page run locally.
- [ ] 1.2 Add a nightly CI workflow on Linux that runs the benchmark and uploads its report. It stays outside the pull-request gate.
- [ ] 1.3 Docs: record the baseline results (in-process parsing), machine type and commit in `docs/benchmarks.md`.
- [ ] 1.4 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.
- [ ] 1.5 Decision: the maintainer reads the baseline in `docs/benchmarks.md` and decides whether groups 2–4 go ahead. They go ahead only if parsing is the bottleneck. **Stop here until the maintainer decides.**
  - Yes: record the decision in `docs/benchmarks.md`, then continue with group 2.
  - No: record the decision in `docs/benchmarks.md`. Groups 2–4 are not implemented: descope them and `specs/crawl-performance/spec.md`, then skip to group 5.

## 2. Parsing in worker processes

- [ ] 2.1 [3+6] Drive "Pages are parsed outside the crawl process": the `spawn` pool, whose initializer imports the registry; extractors and sinks are unchanged.
- [ ] 2.2 [CLI] Drive "The number of parse workers is reported": `parse_workers` in `crawl_started`.
- [ ] 2.3 [Subprocess, Windows in CI] Drive "Pages are parsed in worker processes on Windows (Windows)".
- [ ] 2.4 Docs: document the parse pool (start method, worker count, the unchanged extractor interface) in `docs/architecture.md`.
- [ ] 2.5 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Bounded queue and crash containment

- [ ] 3.1 [3+6] Drive "Fetching waits for slow parsing": the permit semaphore of `concurrency + 2 × parse_workers`.
- [ ] 3.2 [3+6] Drive "A crashed worker is recorded": recreate the pool on `BrokenProcessPool`, resubmit one at a time, and record `worker_crashed`.
- [ ] 3.3 [3+6] Drive "The Crawl continues after a worker crash".
- [ ] 3.4 Docs: document the queue bound and crash handling in `docs/architecture.md`.
- [ ] 3.5 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Shutdown and Windows consoles

- [ ] 4.1 [Subprocess] Drive "No parse worker outlives a completed Crawl": `shutdown(wait=True, cancel_futures=True)`.
- [ ] 4.2 [Subprocess] Drive "An interrupt ends the parse workers": workers ignore SIGINT and SIGBREAK, and the pool shuts down within `020`'s grace period.
- [ ] 4.3 [Subprocess, Windows in CI] Drive "Parse workers open no console window (Windows)".
- [ ] 4.4 Docs: document shutdown and Windows console behaviour (why `060` uses CREATE_NO_WINDOW) in `docs/architecture.md`.
- [ ] 4.5 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Change check

- [ ] 5.1 If the pool went ahead: rerun the benchmark with the pool, and record its results next to the baseline in `docs/benchmarks.md`.
- [ ] 5.2 If the pool went ahead: verify that every `#### Scenario:` in `specs/crawl-performance/spec.md` has exactly one test named after it.
- [ ] 5.3 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 5.4 Review: run the code-review skill on the whole change (against `specs/crawl-performance/spec.md` if the pool went ahead), then refactor with the whole suite green.
