Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

Seams (docs/testing.md):
- **[3+6]**: crawl the fixture site, with test extractors registered through `020`'s public registry, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Subprocess]**: seam 1, a real `spider` process

## 1. Parsing in worker processes

- [ ] 1.1 [3+6] Drive "Pages are parsed outside the crawl process": the `spawn` pool, whose initializer imports the registry; extractors and sinks are unchanged.
- [ ] 1.2 [CLI] Drive "The number of parse workers is reported": `parse_workers` in `crawl_started`.
- [ ] 1.3 [Subprocess, Windows in CI] Drive "Pages are parsed in worker processes on Windows (Windows)".
- [ ] 1.4 Docs: document the parse pool (start method, worker count, the unchanged extractor interface) in `docs/architecture.md`.
- [ ] 1.5 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Bounded queue and crash containment

- [ ] 2.1 [3+6] Drive "Fetching waits for slow parsing": the permit semaphore of `concurrency + 2 × parse_workers`.
- [ ] 2.2 [3+6] Drive "A crashed worker is recorded": recreate the pool on `BrokenProcessPool`, resubmit one at a time, and record `worker_crashed`.
- [ ] 2.3 [3+6] Drive "The Crawl continues after a worker crash".
- [ ] 2.4 Docs: document the queue bound and crash handling in `docs/architecture.md`.
- [ ] 2.5 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Shutdown and Windows consoles

- [ ] 3.1 [Subprocess] Drive "No parse worker outlives a completed Crawl": `shutdown(wait=True, cancel_futures=True)`.
- [ ] 3.2 [Subprocess] Drive "An interrupt ends the parse workers": workers ignore SIGINT and SIGBREAK, and the pool shuts down within `020`'s grace period.
- [ ] 3.3 [Subprocess, Windows in CI] Drive "Parse workers open no console window (Windows)".
- [ ] 3.4 Docs: document shutdown and Windows console behaviour (why `060` uses CREATE_NO_WINDOW) in `docs/architecture.md`.
- [ ] 3.5 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. The 500k benchmark

- [ ] 4.1 Benchmark: add `benchmarks/crawl_500k.py` with its synthetic 500,000-page fixture site. It measures URLs per second, peak memory and crawl file size. Check it on a 10,000-page run locally.
- [ ] 4.2 Add a nightly CI workflow on Linux that runs the benchmark and uploads its report. It stays outside the pull-request gate.
- [ ] 4.3 Docs: record the first results, machine type and commit in `docs/benchmarks.md`.
- [ ] 4.4 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Change check

- [ ] 5.1 Verify that every `#### Scenario:` in `specs/crawl-performance/spec.md` has exactly one test named after it.
- [ ] 5.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 5.3 Review: run the code-review skill on the whole change against `specs/crawl-performance/spec.md`, then refactor with the whole suite green.
