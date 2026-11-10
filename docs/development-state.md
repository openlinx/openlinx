# Development state

Start a fresh session on public `main`: it is the canonical entry point for shared
instructions, development skills, setup and this state map. Each active branch keeps
its own product checkpoint. Read
[AGENTS.md](../AGENTS.md),
[CONTRIBUTING.md](../CONTRIBUTING.md), [CONTEXT.md](../CONTEXT.md) and
[testing.md](testing.md) before changing them.

## Code checkpoints and transport

The main, 022, 023 and 030 entries were verified against local Git and GitHub on
2026-11-05. The 060 entry records tasks 0.1 through 0.5 accepted locally, with independent
review and passing local gates. Task 0.5 adds killed-Crawl and mutation proof on
top of `24099cf2`; its restored focused checks and local gate passed, with proof
and final metadata reviews completed with no findings.
Other streams retain their 2026-11-04 checkpoints and pending work. Historical
checks below apply only to their named commits; they do not validate later
integration or uncommitted work.

| Canonical branch | Code checkpoint | State |
|---|---|---|
| `main` | `27b18e745aba9d606b91067c5fa795c4cdfb8952` | 023 PR #36 merged after 022 PR #39; main CI 41921423999 passed 9/9 |
| `022-add-fetch-policy` | `8a6fd88b78e1e79cd97c3729091233883e804248` | Group 10 accepted; v0.1 complete on branch; draft PR #41 open and mergeable; exact-head CI 42014800275 passed 9/9 |
| `023-fix-code-audit` | `cc684d2def17186291cf7647f1a48ed67513c066` | Complete and archived; exact-head CI 41854123018 passed 9/9; PR #36 merged into main at `27b18e74` |
| `026-add-parse-pool` | `8294855ecfffb9f07094b931ed0d94754d0bf16d` | Unfinished pool/shutdown work |
| `030-add-page-data` | `908e140cce578d1b9efff21be4194e4869e5960f` | Group 12 accepted; C01/C02 closed; exact-head CI 41804474670 passed 9/9; PR #37 open with conflicts; integrate current main before group 4b |
| `040-add-rules` | `330d5730b3e4dad3ba6a5d9285fd89ef61213d98` | Group 11 refactor; integration remains |
| `050-add-query-and-segments` | `bd21fe4164077076076c5e64805e9f80aeb4b434` | Published unfinished snapshot; review fixes remain |
| `060-add-crawl-control` | Task 0.5 slice on top of `24099cf2678f004c160513b0e9fd5eac1831530b` | Tasks 0.1 through 0.5 accepted locally; task 0.5 killed-Crawl and mutation proof with restored focused checks and local gate green; proof and final metadata reviews completed with no findings; next 0.6; task 0.7 open; groups 1–11 Draft; platform CI not yet run |

The published 022 and 030 heads match their local worktrees and PR heads. Their
acceptance evidence is recorded below: 022's v0.1 work and 030's group 12 are
accepted on their branches, but PRs #41 and #37 remain unmerged. The full 030 change
and the published 050 snapshot remain unfinished. Transport alone establishes no
feature acceptance. Tasks 0.1 through 0.5 of 060 have local review and gate acceptance.
Group 0 and the full change remain unfinished, with no 060 platform CI yet.

Shared instructions, canonical skills, development setup and this hand-off have one
entry point on `main`. They are not automatically transplanted to the other
branches. Start on `main`, read this map, then choose the stream. Before first
continuing an older branch, review and
adapt its instructions/setup to its actual code and tests, preserving its own rules.
In particular, 026, 040 and 050 still use the pre-rename package and older interfaces.
Their direct checkouts are not already ported by the shared setup on `main`.
Product integration and rename work remain separate tasks; transporting unfinished
checkpoints does not require a merge of all of `main` into them.

Check current published refs through GitHub or `git ls-remote origin`, and inspect
fetched commits with Git. A checkpoint need not equal the latest branch head:
later setup/docs commits are expected. Verify ancestry and the intervening diff,
for example `git merge-base --is-ancestor <checkpoint> origin/<branch>` followed by
`git log <checkpoint>..origin/<branch>` and `git diff <checkpoint> origin/<branch>`.
The 023 planning checkpoint and unfinished 022/030/050 snapshots are published.
Instruction/setup changes have their own review and PR/CI evidence, separate from
these product checkpoints. Use the relevant PR/CI and coordinator report for actual
setup and fresh-restore results.

[PR #34](https://github.com/openlinx/openlinx/pull/34), 023 group 4, the Crawl's input,
is merged into `main` at `f38d493fd50ebfda7c3fa968945b72d6633b754e`.
The coordinator reports that the exact-head full gate on `731326b5` passed:
1531 tests passed, 7 platform/account skips, mypy for three platforms, OpenSpec
16/16 and Node 1/1. This is separate evidence from the 022 task 9b.9 checks.
The separate 023 group 5 planning checkpoint `1f3dec66` has since been published.

First 022 [PR #39](https://github.com/openlinx/openlinx/pull/39) is merged into
main at `4957b1879f3a13b22ef0e322f2fc15bfc0b12e50`.
[Main CI 41831195325](https://github.com/openlinx/openlinx/actions/runs/41831195325)
passed all nine OS/Python cells on that historical checkpoint. The size and HTTP
redirect support needed by 030 group 4b is already in main through this merge.

023 [PR #36](https://github.com/openlinx/openlinx/pull/36) subsequently merged at
`27b18e745aba9d606b91067c5fa795c4cdfb8952`, the verified local and remote main HEAD.
[Main CI 41921423999](https://github.com/openlinx/openlinx/actions/runs/41921423999)
passed all nine OS/Python cells on that exact merge commit. This post-merge run is
separate from PR #36's source-head CI and does not validate the pending 030 integration.

## Next work by stream

Stream task, design and spec links below point to the reviewed code checkpoints.
Check the chosen branch head for any later changes.

### 022: group 10 accepted; v0.1 complete on branch, PR #41 unmerged

[Tasks](https://github.com/openlinx/openlinx/blob/8a6fd88b78e1e79cd97c3729091233883e804248/openspec/changes/022-add-fetch-policy/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/8a6fd88b78e1e79cd97c3729091233883e804248/openspec/changes/022-add-fetch-policy/design.md),
[fetching spec](https://github.com/openlinx/openlinx/blob/8a6fd88b78e1e79cd97c3729091233883e804248/openspec/changes/022-add-fetch-policy/specs/fetching/spec.md).

Group 10 is accepted at source `255fcf1611a992c91c45a2e0b207c9c570155644`, after
independent Standards and Spec reviews against main `27b18e74` with no unresolved
findings. Its reported local gate passed 1938 tests with 12 platform skips, strict
mypy on three platforms, OpenSpec 15/15 and Node 1/1;
[source CI 42012946895](https://github.com/openlinx/openlinx/actions/runs/42012946895)
passed all nine cells, including the self-signed TLS tests on all three OSes.
Acceptance metadata is committed at `8a6fd88b`, with a separately reported full
local gate of 1938 passed and 12 skipped. The verified
[current-head CI 42014800275](https://github.com/openlinx/openlinx/actions/runs/42014800275)
passed 9/9 on `8a6fd88b78e1e79cd97c3729091233883e804248`.

[PR #41](https://github.com/openlinx/openlinx/pull/41) remains open and Draft;
GitHub reports MERGEABLE/CLEAN. The branch already contains main `27b18e74`, so no
further local main integration is currently needed. The next landing step is Ready
and maintainer merge of #41. All v0.1 tasks are checked; groups 11–14 remain v0.2.

Historical acceptance evidence follows, tied to its own checkpoints.

Group 9 was reviewed at `a2c6b643`. The whole-group Standards and Spec review of
9b covered `a2c6b643...c8384792`, followed by closure of its findings. Group 9b is
accepted through `6398ef80ef81d91c1ea7deaa55836ddf83bc2c68`, where task 9b.19 was
checked in the P2/S2 fix commit after the final local gate and closure of all fresh
review findings. That accepted the pre-PR group; group 10 acceptance is recorded above.

The earlier branch integration took main `82ffcce61f4e3fc800726e8690eedbc4d55b08af`
through merge commit `f56d3bbde820fd6acca46035a9d923052ff1c923`. The earlier
`809d0d66` restored setup only. The integration preserves main's writer/service,
settings and CLI contracts together with 022's fetching semantics and TLS/proxy
dependencies. The stronger guards remain in place; the virtual-clock guard now
recognises an explicit FakeFetcher factory at the service's `fetchers` seam.

Standards S1 is closed in the integration commit: the proxy CLI test independently
pins `[["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]]` while retaining the comparison
with the reader. A lowercase canonical-name mutation failed the new literal assert;
the production names were restored and the focused checks passed.

Spec P2 is closed at `6398ef80ef81d91c1ea7deaa55836ddf83bc2c68`: the first probe's
elapsed window uses monotonic time from its actual send, after any host wait,
rather than wall-clock timestamps.
Standards S2 is closed in the same fix by moving the decision to the module-level
pure function `_pause_end`, following ADR-0006. The manager reported 62 focused
tests passing after that extraction. These runtime and structure fixes are separate
from C03, already closed by the Backstops spec/window alignment and seam guards in
`e00a88ea015e5f81ccaf708ca1ee93a862fabe33`.

The manager reports the final local gate for this source checkpoint passed:
1781 tests passed and 12 skipped, OpenSpec 16/16 and Node 1/1.

[First draft PR #39](https://github.com/openlinx/openlinx/pull/39)
has a successful [CI run 41812691634](https://github.com/openlinx/openlinx/actions/runs/41812691634)
at source commit `6398ef80ef81d91c1ea7deaa55836ddf83bc2c68`: all nine cells passed,
covering Windows, macOS and Linux across Python 3.12–3.14 with the coverage gate.
This actual first-PR matrix closes
task 8.2; its checkbox and this state update are applied together after that result.

The metadata checkpoint `50cbcf6ff453c6c52487d9ddc5c07e97b5f4ca18` also passed
[CI 41815963203](https://github.com/openlinx/openlinx/actions/runs/41815963203),
with all nine OS/Python cells successful. That result predates the measurement
documentation recorded here.

The later Astra pre-merge source review findings were fixed in `ca916d7a` and
`3a47f843ee770f21d5d7e6faa7c41bac61e64768`.
[CI 41824494037](https://github.com/openlinx/openlinx/actions/runs/41824494037)
passed all nine OS/Python cells at `3a47f843ee770f21d5d7e6faa7c41bac61e64768`.
The manager reports the combined local gate passed with 1821 tests passed,
12 skipped and 98.58% coverage. Those checks cover the source fixes, before the
TLS policy documentation revision below; the earlier group 9b and first-PR
results remain historical evidence for their named checkpoints.

Task 6.4 now has the three-OS measurements from
[proof PR #40](https://github.com/openlinx/openlinx/pull/40),
[TLS run 41816962562](https://github.com/openlinx/openlinx/actions/runs/41816962562):
3/3 jobs successful at `232845ede757d4b3a9f46c152809b2a6b5a05478`, with all five
hosts and 20 handshakes per host per store on each OS. The accepted
[measurement evidence](benchmarks.md#tls-handshake) shows extra truststore overhead.
Task 6.4 is complete under revised D5: the observed overhead is accepted while
retaining the TLS spec's OS trust store and certifi fallback only when truststore
cannot be loaded. The user approved this decision on 2026-11-04; it changes no
runtime behaviour. The first draft PR carried groups 1–9 and 9b; group 10 is now
accepted in #41. Task 10.1 verified the retained workspace proxy exception after
023 was archived. Groups 11–14 remain v0.2 work outside this acceptance.

### 023: complete, archived and merged; main CI passed

[Tasks](../openspec/changes/archive/2026-11-04-023-fix-code-audit/tasks.md),
[design](../openspec/changes/archive/2026-11-04-023-fix-code-audit/design.md),
[PR #36](https://github.com/openlinx/openlinx/pull/36).

All groups are complete and archived, and PR #36 is merged. Its exact source head
`cc684d2def17186291cf7647f1a48ed67513c066` passed all nine cells of
[CI 41854123018](https://github.com/openlinx/openlinx/actions/runs/41854123018).
The merge commit `27b18e74` separately passed main CI 41921423999, linked above.
There is no remaining 023 landing or CI blocker.

Historical review evidence: groups 1–4 were already in main; group 5 and the
integration of main `4957b187` were accepted on the branch. Tasks 6.1–6.3 document
the real extension recipes, formula seams, implementation checks and strict-mypy contracts.

The whole-change GPT-6 Astra Standards and Spec review covered groups 1–6,
including the earlier merged groups and current integration. Its three reproduced
findings are fixed: writer batch durability in `575dab4f`, bounded hook-error
redaction in `8778e412`, and caller attribution for empty unknown tables in
`80e97f34761387fbaadcebb0c26ae0dd1365396a`. Independent Astra review accepted each
fix; the reported pre-merge combined local gate passed 1932 tests with 12 platform skips,
strict mypy on three platforms, OpenSpec 16/16 and Node 1/1.

Both CLI self-description scenarios now have separate test names. The four delta
specs map to 46 scenarios, with none missing or duplicated. Whole-change review
closed at `c192f242`. The four primary specs now contain the accepted deltas, and
the change is archived with all tasks complete. The workspace proxy exception
remains intact; 022 task 10.1 verified that retained requirement in `0ff53486`.
Strict validation after the archive passed all 15 remaining active specs and changes.

Source integration `e9eb6dba` passed all nine cells of
[CI 41839157705](https://github.com/openlinx/openlinx/actions/runs/41839157705).
That historical run predates the later docs and fixes; current source-head and
post-merge acceptance are established by the separate runs above.

### 026: reconcile the core, then close bounded shutdown

[Tasks](https://github.com/openlinx/openlinx/blob/8294855ecfffb9f07094b931ed0d94754d0bf16d/openspec/changes/026-add-parse-pool/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/8294855ecfffb9f07094b931ed0d94754d0bf16d/openspec/changes/026-add-parse-pool/design.md).

The pool, bounded queue and crash/deadline handling are committed. The head is task
4.7's cross-Python `PicklingError` fix; 4.2, part of 4.5 and 4.6 remain open.
This branch still uses the pre-rename source package and an older 020 interface. Its latest core merge
is `78019016`, before the completed core and product rename.

Start with a plan check against current `main`: reconcile the package rename and
PageExecutor lifecycle before implementing 4.2. The relevant rename decisions are in
[021 D3](../openspec/changes/archive/2026-10-29-021-rename-to-openlinx/design.md).
The original mechanical rename helper is local tooling, so a fresh clone must not
assume it exists; review the equivalent branch-specific migration before running it.
Preserve the existing Crawl Mode value when renaming the package.

Task 4.2 must bound shutdown when a worker never finishes a Page or never becomes
ready after the pool breaks. Check parent death while a worker is busy too: an idle
pipe read alone cannot end that worker. The PageExecutor contract must return a
Page failure for a worker crash/deadline and reserve a raised error for a broken
contract. Validate through the real pool/subprocess tests in
`tests/crawl/test_parse_pool.py`, then finish shutdown docs and group review.

The 500k baseline was deferred. Before scheduling it, repair the harness's executor
selection and timing interpretation so an in-process baseline really uses that
executor. Baseline/layout measurements and the pool rerun need a quiet machine;
they are not the immediate coding task.

### 030: group 12 accepted; integrate current main before group 4b

[Tasks](https://github.com/openlinx/openlinx/blob/908e140cce578d1b9efff21be4194e4869e5960f/openspec/changes/030-add-page-data/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/908e140cce578d1b9efff21be4194e4869e5960f/openspec/changes/030-add-page-data/design.md).

Groups 1–11 are in main. Group 12 is accepted at source `68fcfeeb`, recorded in
metadata head `908e140cce578d1b9efff21be4194e4869e5960f`, with C01/C02 closed.
[PR #37](https://github.com/openlinx/openlinx/pull/37) is open and ready for review,
but GitHub reports CONFLICTING/DIRTY against current main. Its
[exact-head CI 41804474670](https://github.com/openlinx/openlinx/actions/runs/41804474670)
passed all nine OS/Python cells on `908e140c`. This does not validate a future
integration result; the full 030 change remains unfinished.

Historical acceptance evidence supersedes the earlier blocked checkpoint
`0eeed795`: source
[CI 41749711189](https://github.com/openlinx/openlinx/actions/runs/41749711189)
passed 9/9 on `68fcfeeb`. Independent Standards and Spec reviews found no defects;
the reported full local gate passed 1541 tests with 14 Windows skips, strict mypy
on three platforms, OpenSpec 16/16 and Node 1/1.

- **C01, closed at `ae9f481b`:** `structured_data_error_count` and
  `structured_data_warning_count` agree across the schema, Page record, docs and
  deferred-column test data. Independent literal expectations pin INTEGER,
  nullable shape, v0.3 description prefixes, absent old names and stored NULLs.
- **C02, closed at `68fcfeeb`:** the Windows console helper owns its controlled
  process tree and performs bounded descendant cleanup on timeout. The real guard
  checks termination of `cmd` and two Python descendants before emergency cleanup.
  [Windows mutation proof 41802806574](https://github.com/openlinx/openlinx/actions/runs/41802806574)
  passed on Python 3.12–3.14 at verification commit `5562597f`: original green,
  root-only cleanup red at the surviving-descendants assertion, exact source bytes
  restored, then green again. Verification assets stayed in separate
  [PR #38](https://github.com/openlinx/openlinx/pull/38), closed unmerged.

Next: review the remaining plan, then locally integrate current main `27b18e74`
into 030 before task 4.6. Its current merge-base is `82ffcce6`; reconcile 022's
fetching/size/redirect contracts and 023's Link-reading/type-table changes with
group 12. Preserve the schema, `HttpVersion`, shared Link types/`LINK_TYPES`, Page
records, test helpers and contract tests. Review and gate the integrated result;
the existing green head CI cannot establish acceptance of that result.

022's size and HTTP redirect support is already available in main through PR #39
at `4957b187`; group 4b does not need to wait for PR #41 for that dependency. After
integration, start task 4.6 with compressed Page sizes and the full Page-column
contract, then 4.7, 4.10, docs 4.14 and review 4.15. Shared setup does not perform
this product integration.

Tasks 10.1 (Link layout) and 10.11 (writer capacity) still need a quiet-machine slot.
Share the recorded layout choice with 026 rather than running competing decisions.
Readability, language and HTML storage are later-release work.

### 040: integrate the current core and Page data before adding Rules

[Tasks](https://github.com/openlinx/openlinx/blob/330d5730b3e4dad3ba6a5d9285fd89ef61213d98/openspec/changes/040-add-rules/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/330d5730b3e4dad3ba6a5d9285fd89ef61213d98/openspec/changes/040-add-rules/design.md).

The v0.1 Rule slice and group 11 refactor are committed through `330d5730`. The Rule
reader handles live/stored data, store imports no Rule implementation, and Rule tests
use realistic HTML. This branch still uses the pre-rename source package and has older core/Page data.

Next is an integration plan check for the rename, current core, 023's settings/schema
rules and 030's Indexability. Re-run the Rule populations, reader and pass tests after
that integration. `test_non_indexable_pages_are_not_compared` currently has a strict
xfail conditional on `PageRow` lacking `indexability`; the integration must exercise
the real non-indexable population rather than preserving that condition.

Settle the stop-during-passes contract with 060 before adding cancellation behaviour:
the current core closes its stop signal before passes, and a pass has no stop view.
Check pass-name uniqueness and error attribution in the same plan review. Register
the rules settings table in `services.settings.default_tables()` when taking 023,
and extend its centralized-schema guard to views when integrating Rule views.
Task 10.11 still depends on 060-min resume. The early unchecked title-length tasks
marked v0.2 are not the next v0.1 task.

### 050: close the existing review fixes before group 3

[Tasks](https://github.com/openlinx/openlinx/blob/bd21fe4164077076076c5e64805e9f80aeb4b434/openspec/changes/050-add-query-and-segments/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/bd21fe4164077076076c5e64805e9f80aeb4b434/openspec/changes/050-add-query-and-segments/design.md).

Groups 1 and 2 have implementation commits, with review fixes outstanding. The code
checkpoint includes their plan, `PageRequest` paging (1.19), and the Rule header above
an Issue's table output (1.20). This branch still uses the pre-rename source package and its own
`scripts/check.py`; first continuation needs a reviewed instruction/setup adaptation
that preserves those product files.

Continue in the recorded order: 1.21's CLI guard that jsonl prints only Affected URLs,
1.22's output docs, 1.23's group 1 cleanup, then 2.13's parser limits and review fixes.
Prove each guard by mutation at the agreed seam. For 2.13, reject invalid UTF-8 text,
out-of-range integers, a number joined to a word and excess predicates, and remove
quadratic tokenization. Check `tests/cli/test_issues.py`, `tests/query/test_issues.py`
and `tests/query/test_where.py`.

The current continuity review records two further open findings:

- **C04:** the known 2.13 parser limits and linear tokenizer work remain incomplete.
  The 256-predicate spec limit has no corresponding check, integer digit/range guards
  are missing, and tokenization repeatedly slices the remaining suffix. This is
  existing unfinished work, not a new regression attributed to the last three commits.
  Complete 2.13 before widening use of this parser or accepting the feature.
- **C05:** the Issue table test takes expected `how_to_fix` and `reproduce_sql` from
  the same runtime Rule used to populate its fixture. Use independent literal
  recorded Rule values at the public store seam so a shared source error cannot
  make the test pass. This robustness finding remains open alongside 1.21–1.23.

Then plan the 040 integration. The recorded integration base was `6afd303`; current
040 is its later descendant `330d5730`, whose reader refactor needs explicit conflict
review. In particular, reconcile `decode_detail`, codes and schema declarations.
Reconcile the rename and 023's service contracts in that plan; the where parser
belongs in `query`, its SQL compiler in `store`. Group 3 starts only after this plan
and the existing fixes are reviewed. Groups 9–13 remain v0.2.

### 060: task 0.5 accepted locally; next 0.6

[Tasks](../openspec/changes/060-add-crawl-control/tasks.md),
[design](../openspec/changes/060-add-crawl-control/design.md).

Task 0.1, "A running Crawl keeps its writer claim", is complete locally in the
slice on top of `9cc871ac21d6f9e82812b528ab5e89b38b4ca60e`. Context-managed creation
holds the OS claim around the full start operation; direct callers retain their
post-operation assertions, and the writer throughput script retains ownership
through writer closure. Exclusive creation of the claim file handles id collisions
before SQLite creation without weakening the existing exclusive SQLite create.

Independent Astra review found Standards 0 / Spec 0. The full local
`uv run scripts/check.py` passed on the reviewed source: 1935 tests passed,
12 skipped in 197.23 seconds, coverage 98.42%, strict mypy for three platforms,
OpenSpec 15/15 and Node 1/1. The coordinator independently checked the log and the
16-file candidate manifest. These results precede the acceptance metadata update;
source and tests remain unchanged. Disabling POSIX flock acquisition made the
independent process probe return 0 instead of 10; the source bytes were restored
and the test passed again. Actual Windows/macOS/Linux CI has not run for 060.

Task 0.2, "A completed Crawl releases its writer claim", adds a test on top of
`4f945f844889fb6d3de1bfb7d0f8e6930b31194e`, without changing production code.
The pytest process calls the real Crawl Service against the local fixture site,
checks the returned `completed` state and the existing lock file, then stays alive
while a separate process acquires and releases the OS lock through an independent
platform probe. The coordinator reports independent Standards 0 / Spec 0 review
and has reviewed the test diff.

The test was immediately green. A mutation retained the open locked descriptor
after the Service returned, deferring its close to process exit; the probe exited
10 and the test failed at `assert 10 == 0`. The original source bytes were restored
exactly, and both running and completed claim tests passed (2 tests).

The task 0.2 candidate passed the full local gate: 1936 tests passed, 12 skipped
in 198.01 seconds, coverage 98.39%, strict mypy for three platforms, OpenSpec 15/15
and Node 1/1. This final metadata-only update records that result; its review
is completed with no findings. Actual Windows/macOS/Linux CI has not run for 060.

Task 0.3, "A failed Crawl releases its writer claim", adds a parametrized service
test on top of `14a061c3783533ea6525889c1ea6d3f3236674e6`, without production changes.
The network case uses a closed local port. The fallback-writer case uses the
approved `disk_full_after` SQLite boundary: a Page title outgrows the capped writer,
and a fresh fallback writer records `failed` with `write_failed`. The test pins
`database or disk is full` in the existing diagnostic's `details.error` text,
without comparing SQL or its parameters. Both cases read the preserved Crawl file's
stored `failed` state and let an independent OS probe acquire the claim while the
service's caller remains alive.

Both cases were immediately green. A retention mutation kept the locked descriptor
until process exit, and both failed at probe exit 10. A separate mutation replaced
only the diagnostic's full-disk reason with `database is locked`, and the reason
assertion failed. Both production files were restored byte-for-byte. The restored
focused run passed all four claim cases and the existing post-crawl full-disk test
(5 tests); focused ruff and format checks passed.

The task 0.3 candidate passed the full local gate: 1938 tests passed, 12 skipped
in 200.86 seconds, coverage 98.45%, strict mypy for three platforms, OpenSpec 15/15
and Node 1/1. This metadata-only update records the result; final review is
completed with no findings. Actual Windows/macOS/Linux CI has not run for 060.

Task 0.4, "A failed creation releases its writer claim", adds a creation-service
test on top of `a34f6963600c967020d7fa3ddf702a759d2756f2`, without production changes.
The existing `disk_full_after` boundary gains the opt-in `include_creation=True`;
its default remains False, preserving existing callers. The test fixes the id with
the existing clock and Choice seams. At the real SQLite connection boundary it
observes an existing file with `user_version=0` and a refused independent OS probe,
then SQLite's own `max_page_count` limit causes `SQLITE_FULL` during schema creation.
The error names the expected path; the incomplete SQLite file is removed, the lock
file remains, and another process acquires the claim while the caller stays alive.
This observation establishes task 0.4's prerequisite; task 0.7 stays open.

The initial red run showed that the old boundary skipped creation. After the opt-in
was added, retention of the locked descriptor made the final probe exit 10, and
omitting unlink left the incomplete SQLite file behind; each mutation failed its
guard. Both production files were restored byte-for-byte. The restored focused run
passed 14 tests, including prior claim and creation callers and the default full-disk
fallback; standard strict mypy passed all 333 files. Independent review reported
Standards 0 / Spec 0.

The task 0.4 candidate passed the full local gate: 1939 tests passed, 12 skipped
in 200.73 seconds, coverage 98.48%, strict mypy for three platforms, OpenSpec 15/15
and Node 1/1. This metadata-only update records the result; final review is
completed with no findings. Actual Windows/macOS/Linux CI has not run for 060.

Task 0.5, "A killed Crawl releases its writer claim", adds a subprocess test on
top of `24099cf2678f004c160513b0e9fd5eac1831530b`, without production changes.
A real CLI Crawl reaches the hanging fixture request before a separate OS probe
is refused. The test checks that the Crawl process is still alive, calls
`Popen.kill()`, waits for termination, and runs another independent probe using
the same lock-file path. The POSIX case pins `-SIGKILL`; Windows requires abnormal
nonzero termination. The positive run passed in 0.95 seconds, before the existing
45-second watchdog. Cleanup has bounded waits and no sleeps or retries. This slice
adds neither interrupted recovery nor resume.

The test was immediately green. Disabling OS claim acquisition made its pre-kill
guard fail at `(0, None) != (10, None)`. The production bytes were restored exactly,
and all six claim cases passed in the restored focused run; ruff and format checks
passed, and standard strict mypy passed all 333 files. The coordinator reports
code review without findings; proof and final metadata reviews completed with no findings.

The task 0.5 candidate passed the full local gate: 1940 tests passed, 12 skipped
in 251.11 seconds, coverage 98.50%, strict mypy for three platforms, OpenSpec 15/15
and Node 1/1. This metadata-only update records the result. Actual Windows/macOS/Linux
CI has not run for 060.

Tasks 0.1 through 0.5 are checked. Task 0.6 onward, including 0.7, remains unchecked;
group 0 and the change remain unfinished, and groups 1–11 remain Draft.
Next is 0.6, "An id with a writer claim file is drawn again": preserve exclusive
creation and the existing id collision scenarios. Reserved logs and chosen ids
remain in group 5.
Reconcile later groups against implemented dependencies before using their draft
tasks; integrate 022 group 10 fixes before accepting URL-limit resume.

## Evidence and checks

The checkpoint facts come from Git refs, diffs, tasks, designs and test sources.
C01–C05 were identified during the independent continuity review. C01/C02 are closed
by the 030 evidence above, and C03 by the 022 evidence. C04/C05 remain open at the
recorded 050 checkpoint. Older passing runs do not establish that later spec and
implementation pairs agree, or that a pending integration or the remaining 060 work has passed.

PR #34's gate and the 022 task 9b.9 review/gate above have separate scopes; their
results do not establish acceptance of the remaining fetching, Page data or query
work. Record each outcome against the code checked. Reproducible setup is documented in
CONTRIBUTING. Its platform and fresh-restore results belong to the relevant PR/CI
and coordinator report, rather than a temporary migration checklist in this map.

For a focused run, follow `uv run pytest <test file> --no-cov`. Before a commit,
follow CONTRIBUTING and run `uv run scripts/check.py`; serialize full gates on a
shared machine. Set `OPENSPEC_TELEMETRY=0` before running OpenSpec. CI must supply
the required OS/Python matrix evidence. A task checkbox or an old report cannot
replace a run on the reviewed code.

## Resume in a fresh clone

1. Clone or fetch public `main` and read its AGENTS, CONTRIBUTING, canonical skills
   and this map. Follow its locked contributor setup. Shared instructions are
   maintained on `main`; credentials and global agent tools are installed separately.
2. Inspect current GitHub/Git refs. Locate the chosen stream's code checkpoint in
   its branch history and read any later commits. A missing checkpoint or WIP requires
   recovery from its owner before continuing that slice. The latest branch head need
   not equal this checkpoint.
3. Prepare a separate clean worktree for the chosen canonical stream. Read its own
   AGENTS/CONTRIBUTING, proposal, design, delta specs, tasks, source and test runner.
   Before implementation, review the instruction/setup adaptation needed to use the
   shared main workflows there. Preserve branch-specific facts and boundaries; do
   not assume the old branch already contains the main setup or compatible APIs.
   Keep existing working trees intact and do not merge all of `main` for transport.
4. Resolve that adaptation before running branch-specific setup/check commands.
   In particular, the rename is complete in 022/023/030 but not 026/040/050. Refer to
   the main instructions through a separate checkout or Git while reviewing the
   branch. Local private helper scripts are not a required source of authority;
   the nonportable rename helper is called out above. Install each branch's locked
   environment according to its own contributor documentation.
5. Start with the stated plan check or scenario, preserve the dependency order,
   and record the exact tested commit, commands and outcomes in the next hand-off.
   Recheck the live PR before publishing or merging. This document grants no
   permission to publish or to reuse an old agent session.

The durable sources are the files linked above and the branch history, including
the planning commits `0d209151` (022 group 9b), `1f3dec66` (023 group 5),
`0eeed795` (030 group 12 planning corrections, since accepted through `908e140c`) and
`f64324b8` (050 review fixes).
Keep this checkpoint current when a group is reviewed, published or integrated.
