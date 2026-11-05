# Development state

Start a fresh session on public `main`: it is the canonical entry point for shared
instructions, development skills, setup and this state map. Each active branch keeps
its own product checkpoint. Read
[AGENTS.md](../AGENTS.md),
[CONTRIBUTING.md](../CONTRIBUTING.md), [CONTEXT.md](../CONTEXT.md) and
[testing.md](testing.md) before changing them.

## Code checkpoints and transport

Code checkpoints below identify the application, specs and task state. The main,
022 and 023 entries were verified on 2026-11-05; other streams retain their dated
checkpoints until independently updated. Later transport or metadata commits may
follow a code checkpoint without changing its accepted product scope. The 022 v0.1
work is accepted on its branch; groups 11–14 remain unfinished v0.2 work.

| Canonical branch | Code checkpoint | State |
|---|---|---|
| `main` | `27b18e745aba9d606b91067c5fa795c4cdfb8952` | 023 PR #36 merged; main CI 41921423999 passed 9/9 |
| `022-add-fetch-policy` | `255fcf1611a992c91c45a2e0b207c9c570155644` | Group 10 accepted; draft PR #41 CI 42012946895 passed 9/9; v0.1 complete on branch |
| `023-fix-code-audit` | `c192f242b53c91395dfefde246be6f5e53aec300` | Whole-change review complete; specs synchronized and change archived; PR #36 merged into main at `27b18e74` |
| `026-add-parse-pool` | `8294855ecfffb9f07094b931ed0d94754d0bf16d` | Unfinished pool/shutdown work |
| `030-add-page-data` | `0eeed79504271c7cf1e51ab69543271225c995d8` | Published unfinished snapshot; group 12 acceptance blocked by C01/C02 |
| `040-add-rules` | `330d5730b3e4dad3ba6a5d9285fd89ef61213d98` | Group 11 refactor; integration remains |
| `050-add-query-and-segments` | `bd21fe4164077076076c5e64805e9f80aeb4b434` | Published unfinished snapshot; review fixes remain |

The 030 and 050 checkpoints have been pushed by native Git fast-forward as unfinished
snapshots. No fresh full gate or feature acceptance is claimed for that transport.
The 022 checkpoint is published in PR #41; group 10 review and nine-cell CI
evidence are recorded below. Open findings remain part of each stream's next work. Publishing a ref does not
accept its features or merge it into `main`; transport alone needs no draft feature PR.

Shared instructions, canonical skills, development setup and this hand-off have one
entry point on `main`. They are not automatically transplanted to the six active
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
passed all nine OS/Python cells on that checkpoint. This is incoming-main evidence,
not validation of the current 023 integration.

## Next work by stream

Stream task, design and spec links below point to the reviewed code checkpoints.
Check the chosen branch head for any later changes.

### 022: group 10 accepted; v0.1 complete on branch

[Tasks](https://github.com/openlinx/openlinx/blob/255fcf1611a992c91c45a2e0b207c9c570155644/openspec/changes/022-add-fetch-policy/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/255fcf1611a992c91c45a2e0b207c9c570155644/openspec/changes/022-add-fetch-policy/design.md),
[fetching spec](https://github.com/openlinx/openlinx/blob/255fcf1611a992c91c45a2e0b207c9c570155644/openspec/changes/022-add-fetch-policy/specs/fetching/spec.md).

Group 10 is accepted at `255fcf1611a992c91c45a2e0b207c9c570155644` after independent
Standards and Spec reviews against main `27b18e74`, with no unresolved findings.
[Draft PR #41](https://github.com/openlinx/openlinx/pull/41) has a successful
[CI run 42012946895](https://github.com/openlinx/openlinx/actions/runs/42012946895):
all nine OS/Python cells passed. The self-signed TLS fixture and Crawl tests ran
without skips on Windows, macOS and Linux. The local full gate passed 1938 tests
with 12 platform skips, 99% coverage, strict mypy on three platforms, OpenSpec
15/15 and Node 1/1. Tasks 10.4 and 10.6 are complete; the
[current task record](../openspec/changes/022-add-fetch-policy/tasks.md#10-closing-the-change-v01)
records this acceptance. The PR is not merged. Groups 11–14 remain open for v0.2.

Earlier acceptance evidence follows, tied to its own source checkpoints.

Group 9 was reviewed at `a2c6b643`. The whole-group Standards and Spec review of
9b covered `a2c6b643...c8384792`, followed by closure of its findings. Group 9b is
accepted through `6398ef80ef81d91c1ea7deaa55836ddf83bc2c68`, where task 9b.19 was
checked in the P2/S2 fix commit after the final local gate and closure of all fresh
review findings. This accepts the pre-PR group; the full fetching change remains unfinished.

The branch actually integrates main `82ffcce61f4e3fc800726e8690eedbc4d55b08af`
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
runtime behaviour. The first
draft PR carried groups 1–9 and 9b. Group 10 is now accepted in PR #41 as recorded
above; 10.1 verified the retained proxy contract after 023 was archived. Groups
11–14 are v0.2 work and are outside this acceptance.

### 023: complete, archived and merged

[Tasks](../openspec/changes/archive/2026-11-04-023-fix-code-audit/tasks.md),
[design](../openspec/changes/archive/2026-11-04-023-fix-code-audit/design.md),
[PR #36](https://github.com/openlinx/openlinx/pull/36).

Groups 1–4 are in `main`. Group 5 and the integration of main `4957b187` are
accepted; tasks 6.1–6.3 document the real extension recipes, formula seams,
implementation checks and strict-mypy contracts.

The whole-change GPT-6 Astra Standards and Spec review covered groups 1–6,
including the earlier merged groups and current integration. Its three reproduced
findings are fixed: writer batch durability in `575dab4f`, bounded hook-error
redaction in `8778e412`, and caller attribution for empty unknown tables in
`80e97f34761387fbaadcebb0c26ae0dd1365396a`. Independent Astra review accepted each
fix; the latest combined local gate passed 1932 tests with 12 platform skips,
strict mypy on three platforms, OpenSpec 16/16 and Node 1/1.

Both CLI self-description scenarios now have separate test names. The four delta
specs map to 46 scenarios, with none missing or duplicated. Whole-change review
closed at `c192f242`. The four primary specs now contain the accepted deltas, and
the change is archived with all tasks complete. The workspace proxy exception
remains intact; 022 task 10.1 verified that retained requirement in `0ff53486`.
Strict validation after the archive passed all 15 remaining active specs and changes.

Source integration `e9eb6dba` passed all nine cells of
[CI 41839157705](https://github.com/openlinx/openlinx/actions/runs/41839157705).
That run predates the later docs and fixes. PR #36 was merged into `main` at
`27b18e745aba9d606b91067c5fa795c4cdfb8952`; the resulting
[main CI 41921423999](https://github.com/openlinx/openlinx/actions/runs/41921423999)
passed all nine OS/Python cells.

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

### 030: resolve group 12 contract and cleanup findings first

[Tasks](https://github.com/openlinx/openlinx/blob/0eeed79504271c7cf1e51ab69543271225c995d8/openspec/changes/030-add-page-data/tasks.md),
[design](https://github.com/openlinx/openlinx/blob/0eeed79504271c7cf1e51ab69543271225c995d8/openspec/changes/030-add-page-data/design.md).

Groups 1–11 are in `main`. Group 12 has an earlier review commit `e556abb2` followed
by planning corrections `0eeed795`; the current continuity review found that its
acceptance claims are incomplete. It may be transported as unfinished work.
Resolve these two findings before declaring group 12 accepted or proceeding to 4b:

- **C01, open:** the spec/proposal require `structured_data_error_count` and
  `structured_data_warning_count`, but the schema, Page record, schema/architecture
  docs and test data list still use `structured_data_errors` and
  `structured_data_warnings`. Align the names throughout the public contract and
  independently check the declared schema, NULL values and release prefixes.
- **C02, open:** task 12.3 promises Windows subprocess-tree cleanup on timeout.
  `tests/cli/test_encoding.py` uses `subprocess.run(timeout=...)` on `cmd`, with no
  path that terminates its Python descendants. Implement ownership and cleanup of
  the whole tree and verify that no child survives a timeout. A hang was not
  reproduced during this review; the missing cleanup path was found by reading it.

Then review the corrected group with the Page/Link contract tests, extractor tests,
Windows encoding/cleanup checks and writer throughput smoke test. Group 4b also
waits for 022's size and redirect support in `main`. Its later plan check starts
at 4.6, compressed Page sizes, and covers the full Page-column contract before the
HTTP-redirect slices. Reconcile 023's Link-reading/type-table changes when integrating
the new product base. Shared setup on `main` does not perform that integration.

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

## Evidence and checks

The checkpoint facts come from Git refs, diffs, tasks, designs and test sources.
C01–C05 were identified during the independent continuity review. C03 is closed
by the 022 evidence above. C01, C02, C04 and C05 belong to their streams' documented
checkpoints; check those branches for current status. Older passing runs do not
establish that later spec and implementation pairs agree.

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
`0eeed795` (030 group 12 planning corrections, acceptance blocked) and
`f64324b8` (050 review fixes).
Keep this checkpoint current when a group is reviewed, published or integrated.
