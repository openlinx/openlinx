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

The local integration includes the platform runner fix at `30ca0c46`:
`scripts/check.py` checks Windows, Linux and macOS types explicitly on every host.
These static targets do not establish runtime compatibility on those operating systems.

| Stream | Verified checkpoint | Product state and canonical tasks |
|---|---|---|
| 022 fetching | Local branch through task 11.4 | v0.1 complete through group 10; v0.2 secret recording, scoped header precedence, Accept-Encoding overrides and External/robots header guards implemented locally. Groups 11–14 remain unfinished. [Tasks](../openspec/changes/022-add-fetch-policy/tasks.md). |
| 023 code audit | Merged `cc684d2d` | Complete and archived on main. [Archived tasks](../openspec/changes/archive/2026-11-04-023-fix-code-audit/tasks.md). |
| 030 Page data | Public [86130ead](https://github.com/openlinx/openlinx/tree/86130ead1eca45f7e015a435220344109c42d9b4); local `c31c717e` | Foundation in main; local group 4b, Max-Age, Content Area, sentence-splitting and cookie Domain fixes complete; whole-change acceptance remains open. [Tasks](../openspec/changes/030-add-page-data/tasks.md). |
| 060 Crawl control | Frozen local `5fcf25e2` | Ownership tasks 0.1–0.6 implemented locally and integrated with main; frozen after task 0.6; control Commands are not implemented. [Main draft](../openspec/changes/060-add-crawl-control/tasks.md) has no group 0; current tasks are on the local branch below. |
| 026 parse pool | Public `8294855e` | Older core and pre-rename package; bounded shutdown and scale proof remain. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/8294855ecfffb9f07094b931ed0d94754d0bf16d/openspec/changes/026-add-parse-pool/tasks.md). |
| 040 Rules | Public `330d5730` | Rule slice and reader refactor exist; current core/Page data integration and remaining v0.1 Rules are open. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/330d5730b3e4dad3ba6a5d9285fd89ef61213d98/openspec/changes/040-add-rules/tasks.md). |
| 050 queries | Public `bd21fe41` | Groups 1–2 have implementation, with review fixes and 040 integration outstanding. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/bd21fe4164077076076c5e64805e9f80aeb4b434/openspec/changes/050-add-query-and-segments/tasks.md). |

### Page data and ownership candidates

030 findings **C01 and C02 are closed on public main**, through
[PR #37](https://github.com/openlinx/openlinx/pull/37): the deferred structured-data
count columns are declared and Windows subprocess-tree cleanup is guarded. They no
longer block group 12. The pause-count fix is also in main through
[PR #41](https://github.com/openlinx/openlinx/pull/41).

Local 030 checkpoint `c31c717e00a21662e3eae72ba4f68c6e7ed71c7c` includes Page sizes,
HTTP redirect data, bounded Max-Age parsing and Content Area roots outside the body,
plus linear sentence splitting and IPv6 cookie Domain handling that rejects folded values.
Restore local branch `coord/030-sizes-2026-11-13`; its current task file is
`openspec/changes/030-add-page-data/tasks.md`.
The earlier foundation integration with main `741b92f7` passed the local full check
and supplemental Windows type check. The sentence-splitting and cookie Domain
review fixes are complete locally; group 4b review and whole-change closure remain
governed by the tasks. Cross-OS candidate CI and feature acceptance remain unverified.
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
claim file passed the local full check and supplemental Windows type check. The
stream is frozen after task **0.6**. Task **0.7**, proving ownership before schema
creation, the remaining ownership scenarios and group 0's review with actual
cross-OS CI remain open.
Detached Crawls, `status`, `stop` and `resume` remain planned. Later draft task groups require
reconciliation with the implemented lifecycle before they are built.

### Active fetching plan

Continue on local branch `coord/022-fetch-v02-2026-11-15`; its current tasks are in
`openspec/changes/022-add-fetch-policy/tasks.md`.

022's plan covers groups 11–14: per-hop Internal identity and safe secret
recording/continue inputs, an explicit proxy, bounded offered HTTP capability
measurement via ALPN, and bounded zstd decoding. Tasks 11.1–11.2 are complete locally:
header-aware secret recording, explicit-before-default source precedence, Internal
request headers and persisted User-Agent selection for direct continue. The Seed's
provisional Page and robots classification now agree. The `eab31aed` checkpoint
passed independent review and the local full check (2,107 tests passed, 14 skipped,
98.59% coverage). Remaining runtime work and whole-change acceptance are open.
Task 11.2a adds source-boundary Accept-Encoding validation and literal wire checks
for overrides, including empty and repeated fields. Supported response decoding
remains independent of the advertised preference. The default is still
`gzip, deflate, br`; zstd remains in group 14.
Task 14.8 requires actual Python 3.12–3.14 runtime evidence on Windows,
macOS and Linux; local checks and mypy platform targets do not satisfy it. The resume
Command adapter belongs to 060; Page capability population belongs to 030.

### Continuation and deferred quality work

Tasks 11.3–11.4 add wire guards for External Links, Seed redirects, Internal robots
and robots redirects to External URLs. The guards preserve ordered repeated custom
headers and were proven with failing mutations; no runtime change was needed.
Confirm the actual branch, task marks and checks before continuing.
Continue with 11.5–11.7's per-hop guards and header diagnostics,
then Basic Auth and fresh-secret continue inputs (11.8–11.14), group review, explicit
proxy, offered HTTP capability and bounded zstd. Keep 060 frozen at task 0.6.

Before using sensitive custom headers, finish the pending diagnostic and continue
guards: the current secret collector skips header lists, transport failure messages
can reach stored URL diagnostics unredacted, and fresh-secret restoration is not yet
implemented. Header-aware masking in recorded argv/config does not close these
paths. Tasks 11.7 and 11.12–11.14 own that work. Before Basic Auth implementation,
also make the non-ASCII credential encoding explicit in the owning plan so sending
and diagnostic masking use the same representation.

The [comment review and test quality plan](test-organization-plan.md) separates
comment review, test-contract corrections and file organization. Review preparation
has started; a sample review identified two test-quality candidates that still need
reproduction and correction. It does not establish whole-repository compliance.
Implementation remains deferred until after 022; no test reorganization is part of
this checkpoint. Preserve useful rationale in comments and all regression scenarios
when completing the review and its correction slices.

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
