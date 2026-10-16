> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

Seams (docs/testing.md):
- **[3+6]**: crawl the fixture site through the Crawl Service, with test extractors added to `020`'s `default_hooks()` in `spider.services.hooks`, the composition root, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Subprocess]**: seam 1, a real `spider` process

Group 1 is the benchmark, run against `020`'s in-process executor. Groups 2–4 build the pool, which is unconditional in v0.1 (the user's decision of 2026-10-11).

## 1. The 500k benchmark (baseline)

- [x] 1.1 Benchmark: add `scripts/crawl_500k.py` with its synthetic 500,000-page fixture site, which injects a share of the hostile fixtures' faults, deeply nested `<div>` Pages over the deadline and Pages that end their worker included; the site is seeded, records its injected counts, has a latency option and a direct mode (design D6). It records URLs per second, peak memory, machine-wide CPU and clock frequency, the crawl file's size with each table's share, the WAL peak, and the share of the crawl process's CPU time spent in page preparation, and it fails a run that crashes, grows its memory, or leaves a URL unaccounted for in `urls`. Check it on a 10,000-page run locally. It is done when its three parts are:
  - [x] 1.1a Fixture: the synthetic site and its server process, test-first in `tests/fixture_site/`. The harness gains, additively, a `resolve=` fallback on `Site`, a `Bytes` route kind and a server that keeps no request log. The site is a function of its seed and a Page's number: a Page model rendered to HTML, Links of every Link type, a `fanout` parameter, faults on leaves of its spanning tree, and a manifest of the injected counts with their expected outcomes. It is served from its own `spawn` process, which returns a tally of the requests per Page (design D6).
  - [x] 1.1b Benchmark: `scripts/crawl_500k.py`, run as `uv run python -m scripts.crawl_500k`, once `020` is on `main`: the crawl run against the site's process, the direct mode, the measurements and the soak checks against the manifest, with the extractor that ends its worker added to `default_hooks()`; `docs/benchmarks.md` says how to run it.
  - [x] 1.1c Fixture: the reset fault and the External hosts (about 50 `*.test` hosts through the DNS resolver hook), once `020`'s tasks 5.11 (the route option that resets the connection) and 6.1 (the DNS resolver hook) are on `main`; until then their shares are 0.
- [ ] 1.2 Docs: run the baseline against `020`'s in-process executor, and record its results, the machine and the commit in `docs/benchmarks.md`.
- [ ] 1.3 Check: the crawl-file layout variants (design D6). For the `links` layout, if `030`'s task 10.1 has already chosen it, record that choice; otherwise run 10.1's four layouts and decision rule, and record the choice in the "Links layout" section of `docs/benchmarks.md`, which 10.1 then takes. Also measure a 16 KB page size, a zstd dictionary for stored HTML, and the WAL size of a ~100k-Page run without a concurrent reader, and record them.
- [ ] 1.4 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Page preparation in worker processes

- [x] 2.1 [3+6] Drive "Pages are parsed outside the crawl process".

  Done when: the pool executor in `spider.crawl.parse_pool` implements `020`'s `PageExecutor.prepare(url, response)` with its own `spawn` workers, one Page per worker at a time; each worker starts with the settings snapshot and the registered extractors, and a work item carries only the response (design D1); extractors and handlers are unchanged.
- [x] 2.2 [CLI] Drive "The number of parse workers is reported": `parse_workers` in `crawl_started`, from the physical core count of design D1. Done when: `psutil` is a runtime dependency, imported in `spider.crawl.parse_pool` only, and `tests/cli/test_startup.py` still passes.
- [x] 2.3 [Subprocess, Windows in CI] Drive "Pages are parsed in worker processes on Windows (Windows)".
- [x] 2.4 Docs: document the parse pool (start method, worker count, the snapshot sent once when a worker starts, the unchanged extractor interface) in `docs/architecture.md`.
- [x] 2.5 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.
- [x] 2.6 Review fixes of group 2's review (2026-10-14), each test-first with its cause:
  - a worker whose crawl process has ended returns quietly when it cannot send its outcome, and its outcome's fallback pickling never raises
  - `test_spider_crawl_starts_its_parse_workers` goes: its `>= 1` children also holds for the in-process executor on POSIX, it duplicates `test_a_crawl_marked_parse_pool_prepares_its_pages_in_the_pool`, and it starts `default_workers()` processes
  - the default worker count is pinned against faked machine facts, no longer against a copy of its own code
  - `PoolExecutor.close()` without `start()` returns cleanly (`020` D9: close is idempotent, tolerates a never-started executor, never raises)
  - `docs/architecture.md` no longer says that `default_page_executor()` selects the in-process executor
  - on Windows before Python 3.13 the worker count is capped at 31, as `multiprocessing.connection.wait` waits on at most 63 handles there (a result pipe and a sentinel per worker, and the wake pipe), named in design D1
  - a cgroup v2 CPU quota (`cpu.max`) caps the cores the worker count starts from, in design D1 and `docs/architecture.md`
  - design Risks lists group 2's tests that no scenario names, and the loop thread's pickling of each work item
  - the proposal's `crawl_started` lines say that `020` reports `parse_workers` and this change sets it to the pool's size
- [x] 2.7 Check: `PoolExecutor(workers=n)` refuses, with a `ValueError`, an `n` below 1 or above the waiter's limit on this platform (design D1), as a programmer's error (ruled 2026-10-14).
- [x] 2.8 Check: the settings snapshot is the first message on a worker's task pipe, its two pipe ends its only start arguments (design D1: on Windows a child that dies while it unpickles its arguments would otherwise leave its result pipe open in the crawl process); each worker answers "ready" once it has read the snapshot, before its first Page, and with the error when it cannot, so a worker that ends before it is ready, such as a spawn child that cannot import an extractor's module, makes `prepare()` raise `WorkerStartError`, a Crawl error, and is never replaced; a worker that ends after it is ready is handled as design D3 says (ruled 2026-10-14; it needs nothing of `020`'s task 7.23, so it comes before 3.2).
- [x] 2.9 Check: the waiter sees a worker's end as the end of file on its result pipe, watching no process sentinel (design D1, ruled 2026-10-14): a worker terminated from outside fails its Page promptly; the Windows cap before Python 3.13 becomes 62 workers, in the table test, design D1 and `docs/architecture.md`.
- [x] 2.10 Check: each extractor output crosses from the worker pickled by itself, so an output the crawl process cannot unpickle costs only its extractor (`extractor_error`, the Page's Links kept), as one the worker cannot pickle does (design D3, ruled 2026-10-14).

## 3. Bounded queue and crash containment

- [x] 3.1 [3+6] Drive "Fetching waits for slow parsing": the task slots of `020`'s global request cap + the executor's backlog, 2 × `parse_workers` (design D2), on the single-host fixture site too (ruled 2026-10-14).
- [x] 3.2 [3+6] Drive "A crashed worker is recorded": a dead worker's one Page is `worker_crashed`, and the worker is replaced (design D3).

  Done when: a per-Page failure of the pool never raises out of `prepare()`, which returns a failure `PreparedPage` (no tree, its defaults) with `parse_error` = `worker_crashed` (a worker that ended, a Page record the crawl process cannot read; an output it cannot read is task 2.10's `extractor_error`) or `parse_timeout`, and raises only for a programmer's error, such as a Page before `start()` (ruled 2026-10-14; `020`'s task 7.23 derives the header Links in process and records `parsed` = 0 for these values, and is merged before this task); and a worker that ends after it is ready (task 2.8) is replaced.
- [x] 3.3 [3+6] Drive "The Crawl continues after a worker crash".
- [x] 3.4 [3+6] Drive "A Page that takes too long to prepare is recorded": `PREPARE_DEADLINE_SECONDS`, from the moment a worker takes the Page; the worker over it is killed and replaced, and the URL gets `parse_timeout` (design D8).

  Done when, besides: a worker that has not answered "ready" within the deadline is a `WorkerStartError`, the Crawl's error, and is never replaced, with its own test (a worker that never answers ready; ruled 2026-10-14).
- [x] 3.5 [3+6] Drive "The Crawl continues after a preparation timeout".
- [x] 3.6 [3+6] Drive "Other Pages are not charged for a preparation timeout".
- [x] 3.7 Docs: document the queue bound, crash handling and the preparation deadline (its value, and why it is a constant) in `docs/architecture.md`.
- [x] 3.8 Check: the in-process double prepares a Page as a worker does (design Test seams). `tests/support/page_executor.py` prepares each Page with a pickle round trip of the `PageSettings` given to `start()`, as a worker gets its snapshot (D1), and hands on each extractor output through a pickle round trip of its own, as a worker sends it (D3). A settings snapshot or an output that cannot cross is recorded by the fixture and fails the test at its teardown with the pickling error: an exception raised from `prepare()` would only become the Crawl's error, which a test that does not read the Crawl State would miss, and in the pool such an output costs only its extractor, which a test would not see either. Tested with `pytester`, as the isolation plugin is: an inner test whose extractor's output cannot be pickled, and one whose extractor is a local function, each fails at teardown. Guard: the `PageSettings` of `default_hooks()`'s extractors equals its pickle round trip, so an extractor that `030` or `040` registers, and its settings, can reach a worker.
- [x] 3.9 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.
- [x] 3.10 Refactor (ruled 2026-10-16, group 3's review): the wire codec, what a worker sends for a Page and how the crawl process reads it back, moves from `spider.crawl.parse_pool` to its own module, `spider.crawl.parse_wire`, under public names (`encode_outcome`, `decode_outcome`, `crashed_page`), and `parse_pool` keeps the workers, their sizing and the pool's bookkeeping. Behaviour is unchanged: the codec's tests stay, importing the public names; CONTRIBUTING's size sentence is true again.
- [x] 3.11 Fixes of the approval of group 3 (2026-10-16), each red first or red by mutation:
  - a worker that ended, by a crash or over its deadline, leaves nothing open behind it: its task pipe end is closed, its result pipe end is closed by the waiter once it no longer watches it, its process is killed, joined and closed off the event loop's thread before its replacement starts, and it leaves the pool's list of workers, while a count of the workers started names them and gives `worker_pids`. Otherwise every crash of a long hostile Crawl kept two pipe ends and a process handle until `close()`, and on POSIX (256 file descriptors by default on macOS) a pipe for a replacement would fail, a `WorkerStartError` that ends the Crawl. Tested on every OS: several crashes on one worker leave no dead worker's pipe end or process open
  - two replacements started in one pass of the event loop get different names: the number is taken before the start is awaited
  - the `parse_timeout` and `worker_crashed` messages name the Page's URL
  - a worker found ended when a Page is sent to it leaves the pipes the waiter watches at once, before its replacement joins them, so on Windows before Python 3.13, at 62 workers, the waiter never waits on more than 63 handles; the waiter takes a pipe already removed in its stride
  - the docstring of `tests/crawl/unimportable_in_workers.py` (its module is imported with the snapshot), a stale comment in `tests/crawl/test_parse_pool.py`, design Risks' list of the tests named after no scenario, and CONTRIBUTING's size sentence, which leaves out `spider/store/schema.py`
- [x] 3.12 Fix of the approval of 3.11 (2026-10-16): a retirement that fails ends in a broken pool, never in silence. If closing an ended worker's task pipe end or ending and releasing its process fails, the pool breaks with `WorkerStartError` and the cause, so every waiting Page fails and the Crawl ends with that error, where the retiring task died unread before and a one-worker Crawl hung for good. No replacement is started beside a process that may still run. Tested by replacing the pool's private `_reap` with one that raises (the one seam where the OS's refusal can be had), red first: the Page after the crash waited until its timeout.

## 4. Shutdown and Windows consoles

- [ ] 4.1 [Subprocess] Drive "No parse worker outlives a completed Crawl": each worker gets a stop message and is joined (design D4).
- [ ] 4.2 [Subprocess] Drive "An interrupt ends the parse workers": workers ignore SIGINT and SIGBREAK, and a worker still preparing a Page when the grace period of `020`'s `StopSignal` ends is killed, its URL left `queued`. Done when, besides: `close()` never waits without a bound on a worker, with a test each for a stop while a worker is on a Page that never ends, and for a worker that is never ready after another worker broke the pool (ruled 2026-10-16). `close()` keeps the busy Pages' deadline timers and the workers' readiness timers armed until its workers have stopped, since they are the only bound on a stop during a Page that never ends; 4.2 decides how (the approval of group 3, 2026-10-16).
- [ ] 4.3 Check: a worker over its deadline is replaced at once, never on the end of file of its result pipe: `_overdue` drops it from the workers alive and watched and starts the replacement itself, so a process that inherited the worker's pipe cannot keep the Crawl waiting for good (design D8, ruled 2026-10-16). Tested on POSIX only, with an extractor whose child process inherits the pipe, the skip reason named; on Windows the kill covers it. Design Risks says so in the same task.
- [ ] 4.4 [Subprocess, Windows in CI] Drive "Parse workers open no console window (Windows)".
- [ ] 4.5 Docs: document shutdown and Windows console behaviour (why `060` uses CREATE_NO_WINDOW) in `docs/architecture.md`.
- [ ] 4.6 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Change check

- [ ] 5.1 Rerun the benchmark with the pool, and with each variant of design D6 (the writer's url → id cache, the link extractor's fast paths), and record the results next to the baseline in `docs/benchmarks.md`.
- [ ] 5.2 Verify that every `#### Scenario:` in `specs/crawl-performance/spec.md` has exactly one test named after it.
- [ ] 5.3 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 5.4 Review: run the code-review skill on the whole change against `specs/crawl-performance/spec.md`, then refactor with the whole suite green.
