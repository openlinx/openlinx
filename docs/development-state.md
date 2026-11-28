# Development state

## Release checkpoint

[PR #83](https://github.com/openlinx/openlinx/pull/83) merged at `457a6d14`
on 2026-11-28. The foreground Spider Crawl records the catalogue of 42 built-in
Rules and evaluates the enabled Rules. `linx issues` lists Issues by Rule with
Affected URL counts. `linx issues <rule-id>` lists that Rule's Affected URLs.
The PR passed all nine Windows, macOS and Linux jobs across Python 3.12–3.14.
That run included separate foreground Crawl and Issues processes with the default in-process Page preparation. Task 050.1.13 tracks formal acceptance.

[PR #84](https://github.com/openlinx/openlinx/pull/84) merged at `5c4bce19`
on 2026-11-28. The Issues Pass records the [Health Score](rules.md#health-score)
after a Crawl completes or stops. Its [PR CI matrix](https://github.com/openlinx/openlinx/actions/runs/46102757046)
passed all nine jobs.

[PR #85](https://github.com/openlinx/openlinx/pull/85) merged at `fe2aabec` and covers [meta refresh](page-data.md#redirects). After successful
Page extraction, the first declaration supplies the raw value and must contain
a URL reference for a redirect. The first resolved Link can come from a later
declaration. If Page extraction fails, the first discovered refresh Link can
supply the target.

[PR #86](https://github.com/openlinx/openlinx/pull/86) restored Continue for a Crawl
from the original 18-Rule preview. It retains the recorded thresholds and schema.
New Crawls record Health Score. The [Rules specification](../openspec/specs/rules/spec.md)
contains 24 requirements and 140 scenarios.

| Change | Status at this checkpoint |
|---|---|
| [024 Crawl Modes](../openspec/changes/024-add-list-and-sitemap-modes/tasks.md) | List (`--list`) and Sitemap (`--sitemap`) are v0.2 drafts. In v0.1, `linx crawl <url>` runs a foreground Spider Crawl from one URL Seed. |
| [026 parse pool](../openspec/changes/026-add-parse-pool/tasks.md) | Page preparation runs in-process. The process pool, bounded worker shutdown and the approximately 500k-URL benchmark remain v0.1 work. |
| [030 Page data](../openspec/changes/030-add-page-data/tasks.md) | Page data used by the 42 Rules is in main. Task 6.14 covers meta refresh at this checkpoint. The Links layout and writer-capacity benchmarks and whole-change review remain open. |
| [040 Rules](../openspec/changes/archive/2026-11-28-040-add-rules/tasks.md) | The 42 Rules, their settings, catalogue Commands, saved and live Issue readers, and Health Score are in main. All 122 tasks are complete and the change is archived. |
| [050 queries](../openspec/changes/050-add-query-and-segments/tasks.md) | Both Issues forms are in main. Tasks 1.13–1.15 and the remaining query Commands, including `summary`, `pages`, `page` and read-only `sql`, remain open. |
| [060 Crawl control](../openspec/changes/060-add-crawl-control/tasks.md) | Writer ownership tasks 0.1–0.10 merged in [PR #82](https://github.com/openlinx/openlinx/pull/82). Task 0.11 and `crawl --detach`, `status`, `stop` and `resume` remain open. |
| [080 Agent Skill](../openspec/changes/080-add-agent-skill/tasks.md) | The v0.1 Skill installation and `doctor` Commands are planned. |
| [085 release](../ROADMAP.md#what-each-change-owns) | The v0.1 packaging and publication workflow is planned. |

## Where to verify progress

Use [README](../README.md) and `linx commands` for available behaviour, the
[Roadmap](../ROADMAP.md) for release scope, and the OpenSpec task files for
outstanding work. Check [public main](https://github.com/openlinx/openlinx/tree/main)
and [pull requests](https://github.com/openlinx/openlinx/pulls) for merged work,
[Actions](https://github.com/openlinx/openlinx/actions) for the checks on the
specific revision, and [Releases](https://github.com/openlinx/openlinx/releases)
for published releases. Before continuing a stream, read
[AGENTS.md](../AGENTS.md), [CONTRIBUTING.md](../CONTRIBUTING.md) and
[CONTEXT.md](../CONTEXT.md), then confirm its actual HEAD, diff and tasks.

## Historical checkpoints

The 022 checkpoint was verified on 2026-11-18. Other stream checkpoints date
from 2026-11-15. The records below describe those checkpoints.

### Main and active streams

At the 022 merge checkpoint, public
[main at `62253122`](https://github.com/openlinx/openlinx/tree/62253122476f840e6ba15d3e2b0e1fd8404dab2c)
contains the foreground Crawl, crawl store, fetch policy, completed code audit and
Page data foundation. The integrated Crawl → Issues product path remains unfinished.
A published branch or a local candidate does not establish feature acceptance or CI
coverage of that candidate.

The local integration includes the platform runner fix at `30ca0c46`:
`scripts/check.py` checks Windows, Linux and macOS types explicitly on every host.
These static targets do not establish runtime compatibility on those operating systems.

| Stream | Verified checkpoint | Product state and canonical tasks |
|---|---|---|
| 022 fetching | [PR #42](https://github.com/openlinx/openlinx/pull/42) merged at `62253122` | All 156 tasks complete and archived on main after Standards and Spec review. [Archived tasks](../openspec/changes/archive/2026-11-18-022-add-fetch-policy/tasks.md). |
| 023 code audit | Merged `cc684d2d` | Complete and archived on main. [Archived tasks](../openspec/changes/archive/2026-11-04-023-fix-code-audit/tasks.md). |
| 030 Page data | Public [86130ead](https://github.com/openlinx/openlinx/tree/86130ead1eca45f7e015a435220344109c42d9b4); local `c31c717e` | Foundation in main; local group 4b, Max-Age, Content Area, sentence-splitting and cookie Domain fixes complete; whole-change acceptance remains open. [Tasks](../openspec/changes/030-add-page-data/tasks.md). |
| 060 Crawl control | Frozen local `5fcf25e2` | Ownership tasks 0.1–0.6 implemented locally and integrated with main; frozen after task 0.6; control Commands are not implemented. [Main draft](../openspec/changes/060-add-crawl-control/tasks.md) has no group 0; current tasks are on the local branch below. |
| 026 parse pool | Public `8294855e` | Older core and pre-rename package; bounded shutdown and scale proof remain. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/8294855ecfffb9f07094b931ed0d94754d0bf16d/openspec/changes/026-add-parse-pool/tasks.md). |
| 040 Rules | Public `330d5730` | Rule slice and reader refactor exist; current core/Page data integration and remaining v0.1 Rules are open. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/330d5730b3e4dad3ba6a5d9285fd89ef61213d98/openspec/changes/040-add-rules/tasks.md). |
| 050 queries | Public `bd21fe41` | Groups 1–2 have implementation, with review fixes and 040 integration outstanding. [Checkpoint tasks](https://github.com/openlinx/openlinx/blob/bd21fe4164077076076c5e64805e9f80aeb4b434/openspec/changes/050-add-query-and-segments/tasks.md). |

#### Page data and ownership candidates

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

#### Archived fetching change

The change was archived and merged in [PR #42](https://github.com/openlinx/openlinx/pull/42).
The archive includes the synced
[Fetching](../openspec/specs/fetching/spec.md) and
[Crawling](../openspec/specs/crawling/spec.md) specifications. Groups
11–14 cover per-hop Internal identity, explicit proxy routing and fresh credentials
on continue, offered HTTP capability and bounded response decoding.

Standards and Spec review closed on `ee7ee390`, whose matrix passed.
[Reviewed code](https://github.com/openlinx/openlinx/tree/ee7ee390a67c57acd0b33e469c45940cceffabd4) · [Review CI](https://github.com/openlinx/openlinx/actions/runs/44218956051).

The archived PR head `907f4079` passed all nine Linux, macOS and Windows jobs
across Python 3.12–3.14. [PR matrix](https://github.com/openlinx/openlinx/actions/runs/44228108609).
The main run at merge commit `62253122` passed eight of nine jobs. The macOS
Python 3.12 job failed the ALPN shared-deadline test in `Tests and coverage`.
[Main matrix](https://github.com/openlinx/openlinx/actions/runs/44229494663).

#### Fetching implementation checkpoints

Tasks 11.1–11.2 established header-aware secret recording, per-hop Internal
headers, User-Agent precedence on continue and consistent Seed classification.
Task 11.2a covered empty and repeated Accept-Encoding overrides on the wire.
The selected request preference and the supported response decoders are independent.

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
guards. External Accept-Encoding uses the default, expanded to include zstd in 14.1.
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
proxy password markers before writer/network access. Task 12.6 supplies fresh inputs. Mutation-proven guards cover CLI metadata and the empty-input bypass.
Task 12.4 adds a real authenticated CONNECT fixture and verifies HTTPS requests,
literal tunnel authority/credentials and the absence of proxy auth at the origin.
The fixture rejects missing/wrong credentials and closes idle tunnels and partial
requests during teardown. Four failing mutations prove the guards; existing HTTP
and environment scenarios remain intact. The local full check passed with 2,473
tests and 14 platform skips.

Task 12.2 verifies explicit proxy precedence over the proxy environment variables and
over both wildcard and named-host `NO_PROXY` entries. All twelve HTTP/HTTPS cases
cover the CLI flag and Workspace setting. Selecting the environment proxy first
fails four cases. Applying the bypass to an explicit proxy fails the other eight.

Task 12.3 preserves credential-free explicit proxy URLs in argv and config, and
masks both the original and percent-decoded password in diagnostics. Separate
CLI and Workspace cases retain the environment proxy recording policy.

Task 12.5 verifies that CONNECT carries neither Authorization nor X-Env through
an authenticated proxy. The Internal origin receives both headers, while the
External origin receives neither on its robots.txt and Page requests.

Task 12.6 restores an explicit proxy from fresh continue input. A recorded
password marker requires a fresh value before writer or network access. The
Service preserves unrelated recorded settings and rereads the current environment.

Task 12.7 documents CONNECT and origin header handling alongside explicit proxy
precedence, password masking and fresh continue inputs. The published CLI option
metadata agrees with the Workspace setting and its literal contract.

Task 13.1 records `http_1_1` for each plain HTTP origin when a request starts.
Discovered origins that receive no request stay NULL. The schema describes offered
capability on origins and Pages. Page population belongs to 030.

Task 14.1 adds single-frame incremental zstd decoding with finite output budgets,
including stacked codings. A locked conditional backport supplies the backend on
Python 3.12 and 3.13. Task 14.4 enforces the window limit across backend fast paths.
Task 14.8 records the cross-platform runtime results below.

Task 14.2 reads concatenated and skippable zstd frames across arbitrary input
boundaries. Each decoding call has a finite output budget. Buffered output is
drained before the decoder accepts more input.

Task 13.2 uses a dedicated ALPN handshake to record HTTP/2 capability on a
direct HTTPS connection. The probe uses Crawl DNS routing, the original host
name and the same trust anchors. Ordinary requests remain on HTTP/1.1.

Task 14.3 verifies that incomplete, corrupt and checksum-invalid zstd bodies and
trailing garbage retain the URL failure classification. Each wire fixture has
a valid control, including a response served as two frames.

Task 14.4 checks the advertised zstd window before decoding each frame. Real
8 MiB and oversized-window fixtures cover split headers, complete input and
subsequent frames, with and without a declared content size.

Task 14.5 verifies the exact 20 MiB output and intermediate limits. Real Crawl
responses establish truncation and Page outcomes, while memory checks exercise
the finite native output budget.

Task 14.6 retains the distinctions between supported response codings, what
the request advertised, and the wire budget. The tests cover an unsupported
coding and bounded reads of compressed input.

Task 14.7 documents the supported codings, compressed and decoded size fields,
the 20 MiB wire, intermediate and final caps, and the independent 8 MiB zstd
window limit. The locked install selects the backend for each Python version.

Task 13.3 records HTTP/1.1 capability for TLS listeners that select
HTTP/1.1 and those that select no ALPN protocol.

Task 13.4 verifies that concurrent requests share a single failed origin probe.
Replaying a writer unit returns the same claim result and schedules the origin
once per run.

Task 13.5 measures External origins and origins whose robots.txt request fails
when the Crawl is configured to ignore robots rules.

Task 13.6 verifies that a failed probe preserves URL attempts, the URL limit and
network pause accounting. A failed measurement on continue clears a prior value.

Task 13.7 measures HTTPS capability over an authenticated HTTP CONNECT using
the effective proxy, mapped proxy address and original TLS server name. Origin
identity headers reach the origin only on the ordinary HTTP requests.

Task 13.8 rejects invalid or incomplete CONNECT responses before starting TLS.
The 65,536-byte cap includes the terminating blank line. Ordinary requests
retain their own response and connection error classifications.

Task 13.10 exercises a capability probe with one per-host slot and verifies
that an admitted probe shares the global connection budget with normal requests.

Task 13.9 verifies a single real-time deadline for admission, DNS, TCP, CONNECT
and TLS, including cumulative latency. Cancelling an unfinished TLS upgrade
closes the transport without waiting on the old stream.

Task 13.11 joins an already-cancelling capability worker before closing the
Crawl writer. Tests cover active TLS, pending admission, asynchronous cleanup
and normal completion with a pending measurement.

Task 13.12 pins the live Origins and Page capability descriptions through the
schema Command. The v0.1 deferred wording stays in the historical snapshot.

Task 13.13 documents offered HTTP capability, HTTP/1.1 request transport,
the shared probe deadline and cleanup on completion or stop.

Task 14.8 verified the locked zstd installation, mypy and all 186
focused decoder, Resource and negotiation cases in each of the nine runtime
cells across Linux, macOS and Windows. Python 3.12 and 3.13 used
`backports.zstd` 1.8.0. Python 3.14 used `compression.zstd`.
All focused tests ran and passed at `bd5c37b1`. [CI run](https://github.com/openlinx/openlinx/actions/runs/44200525556).

The integration branch also carries 030 Page data and developer-check changes.
060 still owns the resume Command and its Workspace input handling. It remains
frozen at task 0.6. The continue Service accepts fresh auth, sensitive headers
and explicit proxy credentials. Page capability population belongs to 030.

#### Next quality work

Follow the [comment review and test quality plan](test-organization-plan.md).
Review comments for decisions and non-obvious reasons, then verify the test
contracts at their public seams. Start by reproducing the two recorded
test-quality candidates. Preserve existing regression scenarios and keep
test organization in separate changes.

### Blockers recorded before PR #83

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
