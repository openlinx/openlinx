# Development state

Product checkpoints verified on 2026-11-15 against public refs and local candidate
files. [README](../README.md) describes available behaviour;
[ROADMAP](../ROADMAP.md) owns release scope and build order. Before continuing a
stream, read [AGENTS.md](../AGENTS.md), [CONTRIBUTING.md](../CONTRIBUTING.md) and
[CONTEXT.md](../CONTEXT.md), then confirm its actual HEAD, diff and tasks.

## Main and active streams

Public [main at `741b92f7`](https://github.com/openlinx/openlinx/tree/741b92f7f0d8b3f3e0bf868bb9d2cb7fa79412ce)
contains the foreground Crawl, crawl store, fetch policy, completed code audit and
Page data foundation. The integrated Crawl → Issues product path remains unfinished.
A published branch or a local candidate does not establish feature acceptance or CI
coverage of that candidate.

The local `fix-check-platforms` branch at `30ca0c46` makes `scripts/check.py` check
Windows, Linux and macOS types explicitly on every host. Main's runner still checks
the host, Linux and macOS, so on Linux it misses Windows. Until that fix is integrated,
also run `uv run mypy --platform win32 --cache-dir .mypy_cache/win32` on Linux.

| Stream | Verified checkpoint | Product state and canonical tasks |
|---|---|---|
| 022 fetching | Main `741b92f7` | v0.1 complete through group 10; groups 11–14 deferred to v0.2. [Tasks](../openspec/changes/022-add-fetch-policy/tasks.md). |
| 023 code audit | Merged `cc684d2d` | Complete and archived on main. [Archived tasks](../openspec/changes/archive/2026-11-04-023-fix-code-audit/tasks.md). |
| 030 Page data | Public [86130ead](https://github.com/openlinx/openlinx/tree/86130ead1eca45f7e015a435220344109c42d9b4); local `9f4354e6` | Foundation in main; local group 4b, Max-Age and Content Area fixes integrated with main and locally checked; whole-change review remains open. [Main tasks](../openspec/changes/030-add-page-data/tasks.md). |
| 060 Crawl control | Local only `5fcf25e2` | Ownership tasks 0.1–0.6 implemented locally and integrated with main; control Commands are not implemented. [Main draft](../openspec/changes/060-add-crawl-control/tasks.md) has no group 0; current tasks are on the local branch below. |
| 026 parse pool | Public `8294855e` | Older core and pre-rename package; bounded shutdown and scale proof remain. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/8294855ecfffb9f07094b931ed0d94754d0bf16d/openspec/changes/026-add-parse-pool/tasks.md). |
| 040 Rules | Public `330d5730` | Rule slice and reader refactor exist; current core/Page data integration and remaining v0.1 Rules are open. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/330d5730b3e4dad3ba6a5d9285fd89ef61213d98/openspec/changes/040-add-rules/tasks.md). |
| 050 queries | Public `bd21fe41` | Groups 1–2 have implementation, with review fixes and 040 integration outstanding. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/bd21fe4164077076076c5e64805e9f80aeb4b434/openspec/changes/050-add-query-and-segments/tasks.md). |

### Page data and ownership candidates

030 findings **C01 and C02 are closed on public main**, through
[PR #37](https://github.com/openlinx/openlinx/pull/37): the deferred structured-data
count columns are declared and Windows subprocess-tree cleanup is guarded. They no
longer block group 12. The pause-count fix is also in main through
[PR #41](https://github.com/openlinx/openlinx/pull/41).

Local 030 checkpoint `9f4354e68013c9e357b44f4bab36830ef10efa7b` adds Page sizes,
HTTP redirect data, bounded Max-Age parsing and Content Area roots outside the body.
Restore local branch `coord/030-sizes-2026-11-13`; its current task file is
`openspec/changes/030-add-page-data/tasks.md`. The main task link above does not
record local group 4b completion.
Its integration with main `741b92f7` passed the local full check and supplemental
Windows type check. Group 4b review and whole-change closure remain governed by the
tasks; cross-OS candidate CI and feature acceptance remain unverified.
Whole-change review found two fixes still needed: sentence splitting repeatedly
rescans a run of punctuation, blocking in-process Page preparation quadratically;
cookie Domain validation drops IPv6 despite the specification's IP-address contract.
The first unresolvable meta refresh followed by a valid one is already an explicit
design Risk; reconcile the specification's wording with that accepted limitation.
Tasks 10.1 and 10.11 still require the Links layout and writer-capacity benchmarks
on a quiet machine at a time chosen by the maintainers. Task 4.15 also requires
shortening the design's guard-test Risks entries before archival.

Local 060 checkpoint `5fcf25e28ec9d81fc005ae8e9142f9e568afdb6b` holds the writer
claim through Crawl creation and execution and tests release on completion, failure,
creation failure and process death. Restore local branch `060-add-crawl-control`;
its current tasks, including group 0, are in
`openspec/changes/060-add-crawl-control/tasks.md`.
Its integration with main `741b92f7` and task 0.6's guard for an existing writer
claim file passed the local full check and supplemental Windows type check. Next
is task **0.7**, proving ownership before schema creation, followed by the remaining
ownership scenarios and group 0's review with actual cross-OS CI. Detached
Crawls, `status`, `stop` and `resume` remain planned. Later draft task groups require
reconciliation with the implemented lifecycle before they are built.

## What blocks Crawl → Issues

1. **Port 026, 040 and 050 to current contracts.** Their public checkpoints still use
   the pre-rename package and older core/store interfaces. Preserve their product work while
   reconciling the rename, settings tables, schema and PageExecutor lifecycle.
2. **Close 026 shutdown before relying on detached workers.** Task 4.2 still needs
   bounded shutdown for a Page that never finishes and a worker that never becomes
   ready after the pool breaks. The current close path cancels deadline/readiness
   timers before an unbounded join; busy-worker parent death is also unresolved.
   Finish shutdown documentation/review, then validate the benchmark harness's
   executor selection before claiming the roughly 500k-URL baseline.
3. **Integrate 040 with current Page data.** Task 5.10's strict conditional xfail
   awaits real non-indexable populations; Indexability is now available in main.
   Redirect tasks 7.2–7.4 and canonical/noindex tasks 8.5–8.11 remain open. Register
   Rule settings with the current service and preserve schema/view guards. Task
   10.11 depends on 060 resume retaining recorded configuration.
4. **Finish 050's existing review work.** Tasks 1.21–1.23 cover the jsonl output
   guard, documentation and cleanup. Task 2.13 still needs UTF-8, signed-integer and
   256-predicate limits plus linear tokenization (**C04**). The Issue table test
   derives expected fix text and SQL from its runtime Rule (**C05**); replace those
   expectations with independent literals at the public seam. Reconcile 040's reader
   before widening queries.
5. **Prove the integrated path.** Exercise a foreground Crawl → Issues on all three
   supported operating systems after the streams are integrated; then measure the
   full pipeline at scale. Branch-local implementation is not that end-to-end proof.

060 owns writer claims and Crawl control; 026 owns worker lifecycle; 040 owns Rule
passes. Before implementing stop during passes, reconcile their contract: the current
core closes its stop signal before passes, and passes have no stop view. Writer
ownership alone does not provide pass cancellation or bounded worker shutdown.
Keep these decisions in the owning changes' design/specs and preserve their guards.

Verify later published refs with `git ls-remote origin`; compare ancestry and diffs
against the checkpoints above before choosing the next task. Operational schedules
and validation transcripts belong outside this product map.
