# Development state

## Release checkpoint, 2026-11-25

Public `main` at `e50fb0ce` contains the foreground Crawl, the archived 022
fetch policy and 023 code audit, and the 030 Page data implementation through
group 4b. Python 3.12, 3.13 and 3.14 each passed on Linux, macOS and Windows.
[Main CI](https://github.com/openlinx/openlinx/actions/runs/44448078238).

The local release branch is `integrate/v01-crawl-issues`. At `91e1b7d2` it was
65 commits ahead of main. Its Linux full check passed with 2,858 tests and 15
platform skips. The three mypy targets passed. The first CI candidate,
`ci/v01-crawl-issues` at `d6a1d577`, brings the 060 ownership work forward on
that base. Its Linux full check passed with 2,867 tests, 15 platform skips and
97.62% coverage. All nine jobs passed on Ubuntu, macOS and Windows with Python
3.12, 3.13 and 3.14 in the
[candidate CI run](https://github.com/openlinx/openlinx/actions/runs/45503809104).
Each job also ran both console scripts from the built wheel with `--version`.
The three-Command acceptance test is still open.
[Build order and release scope](../ROADMAP.md#build-order).

| Change | Where work stood at the checkpoint | Next acceptance condition |
|---|---|---|
| [026 parse pool](../openspec/changes/026-add-parse-pool/tasks.md) | The release branch includes the separate-process synthetic fixture from `b781f2d9`. The default Page executor still runs in-process. The older pool implementation is at `8294855e`. | Port the benchmark harness and worker lifecycle to the current package. Verify bounded shutdown with busy and unready workers and worker exit after parent death. Record the in-process baseline at roughly 500k URLs and verify the default pool before 050 task 1.13. |
| [030 Page data](../openspec/changes/030-add-page-data/tasks.md) | Main includes the group 4b changes, sentence-splitting and cookie Domain fixes. | Run the Links layout comparison (10.1), then the writer capacity benchmark on the chosen layout (10.11). Close the design Risks and whole-change review (4.15). |
| [040 Rules](../openspec/changes/040-add-rules/tasks.md) | Five Rules evaluate real populations on the release branch: `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing` and `h1-missing`. Four further catalogue entries still return no rows by design. | Cover the analysed-Page boundary for `h1-missing`. Widen to the 15 executable v0.1 Rules and the Health Score. The roadmap lists the release Rules by id. |
| [050 queries](../openspec/changes/050-add-query-and-segments/tasks.md) | Tasks 1.1–1.8 are integrated. `linx issues` and the Issue detail Service exist. The Service returned the recorded threshold of 70 after the Workspace threshold changed to 85. | Verify recorded guidance, reproducing SQL, Affected URL detail and cursor isolation between Crawls. Add the singular `issue` Command and its usage hints. |
| [060 Crawl control](../openspec/changes/060-add-crawl-control/tasks.md) | Ownership tasks 0.1–0.6 from `5fcf25e2` are in the first CI candidate at `d6a1d577`. | Prove the writer claim precedes schema creation (0.7). Complete ownership, detached Crawls, `status`, `stop` and `resume`. A resumed Crawl with recorded secret markers needs fresh inputs under the 022 contract. |

## What blocks Crawl → Issues

1. Complete the singular Issue Command through 050 task 1.12 and the 026
   prerequisites in the table. The first scale run records the in-process
   baseline. The acceptance Crawl uses the default pool.
2. On Linux, macOS and Windows, run `linx crawl`, `linx issues` and
   `linx issue internal-4xx` as separate processes against one fixture Crawl.
   Assert one Affected URL each for `title-missing` and `internal-4xx`, then
   the fixture's exact `/e2e/gone` URL with `{"status_code": 404}`. Follow
   with the query documentation and group review (050 tasks 1.13–1.15).
3. For v0.1, finish the 030, 040 and 060 work above and add read-only `sql`,
   `summary`, `pages` and `page`. Generate the 080 Skill from the finished
   Commands, including the SQL cookbook, `skill install` and `doctor`.
4. Re-run the roughly 500k-URL benchmark on the complete pipeline, sweep worker
   counts and record live Issues latency and file sizes. The planned 085 change
   owns the build, release checks and wheel-install smoke on all three systems.
   The full-pipeline run and 085 are still open.

The 030 Page extraction seam reproduced an Indexability error. With a first
meta refresh to `javascript:void(0)` and a second to `/second`, it recorded
`/second` as the redirect target and the Page as `non_indexable`. A first
reload without a URL and a first valid redirect gave the expected results.
Task 4.15 must reconcile this exception with the first-element contract.
[030 design risks](../openspec/changes/030-add-page-data/design.md#risks--trade-offs).

Stop during post-crawl passes crosses three changes. The Crawl core currently
closes its stop signal before passes. The existing final-pass regression
confirms that a late stop leaves a completed Crawl with its original result.
060 must report the targeted run's actual end and keep the stop request from
reaching a successor. 026 owns worker shutdown and 040 owns materialisation.

The 026 port has an additional Linux shutdown case to close before selecting
the pool by default. With one interrupt, a worker held inside a native call
exited and the Crawl left its URL queued. With two interrupts, the owner
exited with code 130 but a worker was still alive after the 10-second check.
This occurred both during preparation and while a new worker read its settings
snapshot. Verify both cases against the integrated pool on each supported OS.

The HTTP benchmark preflight on seed 83 requested 105 Page addresses. One
bodyless HTTP 500 had a URL outcome and no HTML Page. The Store contained 104
Pages and all 2,275 expected URLs. Replacing one Resource URL while preserving
the row count failed verification. The 10k and 500k runs are still open.

On the first CI candidate, the three-process acceptance preflight completed
the fixture Crawl and found one Affected URL each for `title-missing` and
`internal-4xx`. The singular Command exited with `usage_error` because `issue`
has yet to be registered. Task 050 1.13 remains open.

## Test review at this checkpoint

In the integration with 060 ownership and 050 task 1.8, 201 Python test modules
contain 1,586 test functions before parametrisation. Inspection found no empty
test bodies, always-true literal assertions or equality comparisons of an
expression to itself. Of the 14 functions without a direct assertion or
exception expectation, each delegates to an assertion helper, checks a child
process or runs Page extraction over generated inputs with extractor failures
checked by the helper. The release-path review also used deliberate changes.
Reading the installed Rule threshold yielded 60 instead of the recorded 70.
Removing the analysed-Page predicate returned an extra 404 for `h1-missing`.
Replacing a stored Resource while preserving the count failed URL accounting.

Four registered Rules still use empty-result SQL. Of these, `title-too-long`
belongs to v0.1. The other three (`h2-missing`, `low-word-count` and
`url-parameters`) are outside the release's 15 Rules. Ten of those 15 still
need executable queries and tests distinguishing affected and unaffected URLs.

## Planning estimate at this checkpoint

Allow 1–3 working weeks for the foreground Crawl → Issues milestone on the three
supported systems, and 5–9 working weeks from this checkpoint for v0.1. Both
ranges assume the three implementation streams can continue in parallel and a
quiet machine is available for the scale runs. Update the forecast after the
500k in-process baseline, the default pool shutdown tests and task 050 1.13.
A release candidate still needs the full-pipeline benchmark, the remaining
Commands and the 085 wheel install check that runs `linx doctor` with the
pinned Python on all three systems.

## Historical verification of 022 (2026-11-18)

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

### Fetching implementation checkpoints

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
