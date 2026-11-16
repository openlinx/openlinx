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
| 022 fetching | Integration branch with tasks 12.1 and 12.4 | v0.1 complete through group 10; v0.2 scoped request identity, safe fresh auth/header continue inputs and explicit proxy routing with authenticated HTTPS tunnel guards implemented. Groups 12–14 remain unfinished. [Tasks](../openspec/changes/022-add-fetch-policy/tasks.md). |
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
Task 11.5 extends those guards to Checked Internal URLs outside the Seed's folder,
robots and Page retries, and the Seed outage probe. Literal wire logs and stored
Scope/attempt fields prove the requests' roles; pause/resume events distinguish the
probe from the ordinary Seed request. Each path was proven with a failing mutation.
Task 11.6 guards malformed split/joined header inputs before network access and
selective masking in the complete recorded argv/header list. Harmless values,
names, repetitions and order remain intact; failing mutations prove the guards.
Task 11.7 collects sensitive header values for diagnostic masking and redacts
transport failures before URL and robots consumers retain them. Regression tests
cover emitted/stored hook warnings, DNS failures and direct URL protocol failures;
harmless diagnostic context remains visible.
Task 11.8 adds `--auth` and `crawl.auth`, preemptive Internal Basic Auth with exact
UTF-8 bytes, whole-secret recording and resolved Authorization conflict rejection
before writer/network access. Invalid input uses source-specific errors without
quoting credentials. Explicit empty auth overrides Workspace credentials and records
as null. Literal wire cases and failing mutations cover Unicode, empty parts,
whitespace, validation, conflict detection and secret metadata. A DNS-boundary
regression guards the new credential's plaintext and encoded forms in stored errors;
task 11.12 extends it to the complete diagnostic matrix.
Task 11.9 guards Basic Auth and custom Authorization on External Links and on both
Seed and ordinary Internal redirects to an External target. Literal HTTP logs and
stored classification/redirect links establish that each target was requested without
credentials. Failing mutations prove the Internal gates; existing custom-header
guards remain intact. No runtime change was needed.
Task 11.10 extends the auth guards to Internal robots, robots redirects to External
URLs, Checked Internal URLs outside Scope, separate robots and Page retries, and the
Seed outage probe. Literal request logs, stored classifications/attempts and pause
events establish each path's role. Six failing mutations exercise the auth assertions
independently of the retained header assertions; no runtime change was needed.
Task 11.11 guards whole-secret auth recording in split and joined argv, including
URL-shaped credentials, while preserving harmless arguments and header order.
Workspace credentials are verified on the wire; auth/Authorization conflicts across
both flag/Workspace directions fail before HTTP or Crawl-file creation. Failing
mutations prove recording, Workspace loading and conflict rejection; no runtime
change was needed.
Task 11.12 guards raw credentials, nonempty passwords, Base64 payloads and full Basic
values in emitted/result/stored hook diagnostics and URL/robots transport failures.
ASCII, non-ASCII and decomposed Unicode use literal expectations; a direct HTTP
protocol failure separately proves the URL path. Harmless context stays visible.
Nine failing mutations prove the masking paths, individual secret forms and exact
UTF-8 encoding; no runtime change was needed.
Task 11.13 requires fresh auth through `CrawlOverrides.auth` when enabled credentials
were recorded. Missing input raises `secrets_required` (exit 2) before writer/network
access; invalid fresh input is refused without quoting it. Fresh auth is sent on the
wire, collected for diagnostic masking and recorded as `***` again. Explicit null or
empty auth disables it, and recorded null needs no fresh input. Request-policy
validation checks its own header data without treating the secret marker as auth.
Read-only files, request logs and failing mutations prove the refusal order and
masking; the code and service behaviour are documented in the same slice.
Task 11.14 restores fresh sensitive headers by case-insensitive name and occurrence,
retaining recorded name case, positions and harmless bytes. Missing values fail with
`secrets_required`; malformed, extra, harmless or reserved-marker inputs fail with
`invalid_value` before writer/network access. Explicit empty values remain valid.
Real requests and stored records guard repeated continues, both User-Agent winners,
Internal Accept-Encoding overrides, unchanged Workspace-independent settings,
auth/Authorization conflicts and diagnostic masking. Named mutations prove the
guards. External Accept-Encoding still uses the current `gzip, deflate, br` default;
adding zstd remains group 14.
Confirm the actual branch, task marks and checks before continuing.
Task 11.15 verifies the header/auth examples, Workspace and CLI metadata, and config
JSON documentation. The docs distinguish the implemented continue service from the
planned resume Command and explain that a continued default User-Agent follows the
running tool version.
Group 11 review (11.16) is complete locally. Split argv values that resemble flags
are consumed once under their original secret policy, preserving the following
harmless arguments. Page preparation messages mask reflected header and encoded-auth
secrets before URL recording and warning construction. Public CLI/HTTP/SQLite
regressions exposed both leaks before the fixes. The invalid request-policy guard
now uses real HTTP and writable/read-only files instead of a Fetcher double; all
original metadata cases remain. Named failing mutations prove the argv and refusal
guards. Independent Standards and Spec review found no remaining issues in the fixes.
Task 12.1 adds `--proxy` and `crawl.proxy` with URL-form password redaction.
Schemeless inputs use HTTP; an empty flag overrides the Workspace proxy and returns
to current environment handling, including `NO_PROXY`. A continue refuses recorded
proxy password markers before writer/network access; fresh proxy inputs remain in
12.6. Mutation-proven guards cover CLI metadata and the empty-input bypass.
Task 12.4 adds a real authenticated CONNECT fixture and verifies HTTPS requests,
literal tunnel authority/credentials and the absence of proxy auth at the origin.
The fixture rejects missing/wrong credentials and closes idle tunnels and partial
requests during teardown. Four failing mutations prove the guards; existing HTTP
and environment scenarios remain intact. The local full check passed with 2,473
tests and 14 platform skips.

[Draft PR #42](https://github.com/openlinx/openlinx/pull/42) publishes the integration
branch, including 030 and developer-check changes. Its checks track actual candidate
CI; local checks alone do not establish cross-platform runtime compatibility.

Continue with the HTTP/HTTPS precedence matrix in 12.2, then the remaining proxy tasks,
offered HTTP capability
(group 13) and bounded zstd (group 14). Final code review is deferred until the end
of 022; keep its review tasks open until performed. Keep 060 frozen at task 0.6.

Fresh auth and sensitive-header restoration now belong to the continue service.
The resume Command and its Workspace/provenance adapter remain owned by 060;
explicit proxy secrets remain in group 12. The encoding and disabled-auth semantics
are explicit in the owning plan's D1/D8 and fetching specification.

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
