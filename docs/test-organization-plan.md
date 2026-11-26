# Comment review and test quality plan

The first whole-suite review covered all 177 Python test modules collected on
Linux at `dc048245`. Some confirmed findings still await corrections. The comment
review also includes source files and test support outside that count.

The goal is to make tests easy to find and understand while preserving every
existing contract and regression guard. Keep the public seams and boundary doubles
in [testing.md](testing.md). TDD's refactoring step includes test clarity; it does
not require one directory per change, one test per private function, or one assertion
per test.

## Review work before reorganization

- [ ] Review comments and docstrings against [AGENTS.md](../AGENTS.md): preserve
  non-obvious reasons, invariants and design decisions; identify stale claims and
  text that only repeats the code. Check design citations against their owning
  decisions. Record each finding with its location, reason and proposed action;
  do not treat blanket deletion or shorter text as the goal.
- [ ] Review tests against [testing.md](testing.md): map each scenario or regression
  guard to its public seam, inputs, independent literal expectations and permitted
  boundary doubles. Identify tests coupled to private implementation, assertions
  derived from the code being tested, unrelated behaviours bundled together and
  setup that hides meaningful inputs. Source-inspection repository guards require
  a different assessment from product behaviour tests.
- [ ] Record red/green or mutation evidence where available. Missing historical
  evidence is unknown, not proof that a test violated TDD. Prove any new guard
  that passes immediately with a named failing mutation, then restore the code.
- [ ] Turn confirmed findings into small correction slices after 022. Keep comment
  edits, assertion/helper changes and pure file moves separate. Each slice keeps
  scenario traceability, parameterized cases and the existing quality gates, gets
  independent review and passes the required check before commit.

Start with hooks, writer, network-pause, code-style and request-header tests, then
record which areas remain unreviewed. A sample review does not establish whole-suite
compliance. Completion requires an accounted-for review scope, resolved findings
and verified scenario coverage, not merely a green suite or a new directory tree.

### Findings to verify and correct

The initial sample review found two test-quality candidates, confirmed by source
inspection only. Reproduce them before changing tests; neither establishes a
historical failure to follow red/green.

- [x] In `tests/test_code_style.py`, two new tests reproduced a gap in
  `fake_clock_with_real_io`: `crawl_result` and `continued` use aiohttp when
  `fetcher=None` and no factory is supplied. Timing tests can use
  `crawl_result(seed, clock=clock, fetcher=FakeFetcher(clock, pages))`. An explicit
  FakeFetcher factory takes precedence over `fetcher=None`. With a FakeClock,
  the guard now rejects
  that real-I/O path while preserving permitted FakeFetcher cases.
- [x] In `tests/crawl/test_network_pause.py`, the 1800-second case of
  `test_probes_back_off_to_once_a_minute` now asserts all 33 literal probe times,
  from 5 to 1780 seconds. Changing the probe interval from 60 to 61 seconds
  made `1800-times7` fail when the fifth probe moved from 100 to 101 seconds.

The preparatory comment sample found no actionable defect. The completed pilot
below identified two wording and assertion-alignment issues. Preserve the
explanations of handler type checking and writer savepoint cost. Keep the
documented SQL-batching and replay tests permitted by [testing.md](testing.md).

### Post-022 pilot

On Linux at the 022 merge commit `62253122`, the pilot reviewed all functions
and comments in [hooks](../tests/crawl/test_hooks.py), [writer](../tests/store/test_writer.py),
[network pause](../tests/crawl/test_network_pause.py), [code style](../tests/test_code_style.py)
and [request headers](../tests/crawl/test_request_headers.py). All 268 collected
cases from 207 test functions passed. Their exact node IDs, including parameter
IDs, matched the full Linux collection. The pilot covered 5 of 177 collected
Python test modules. At that point, 172 modules and 2,403 of 2,671 node IDs remained.

Four isolated mutations exposed gaps in existing tests:

- [ ] In the [Hook row-value test](../tests/crawl/test_hooks.py), dropping the `values` Handler's
  row for `/a` passed the row-value comparison. Check the exact URL set and row
  count before comparing values. [Per-response hook contract](../openspec/specs/crawling/spec.md#requirement-per-response-hook)
- [ ] In the [Writer window test](../tests/store/test_writer.py), dropping the 2,000th submitted
  unit passed the test that checks whether `run` consumes a window slot. Check
  that all accepted units complete after the held unit is released. [Writer contract](../openspec/specs/crawl-store/spec.md#requirement-submitting-units-with-their-outcome-at-the-commit)
- [ ] The [insert_urls guard](../tests/test_code_style.py) passed when the
  Seed insert bypassed the helper with an inline statement in `store/urls.py`.
  The CLI regression failed with exit 70. Add inline positive and negative
  cases for the module that owns the helper. [022 D2](../openspec/changes/archive/2026-11-18-022-add-fetch-policy/design.md#d2-redirects-are-url-rows)
- [ ] The [TID251 guard](../tests/test_code_style.py) passed with the same glob
  in both Ruff ignore tables when only `per-file-ignores` contained TID251.
  Ruff still suppressed TID251. Check rules from both tables for that glob.

In [code style](../tests/test_code_style.py), describe the leaf `crawl.urls`
module's absence of OpenLinx imports and the resulting lack of a module-level
cycle. In [hooks](../tests/crawl/test_hooks.py), keep the explanation of the
recording-failure hint and align the first-URL comment with a check that observes
the warning's `first_url` field. Keep the explanations of
[typed Hook factories](testing.md#hook-type-contracts) and
[optimistic Writer replay](testing.md#narrow-implementation-checks).

The next batch covered [Hook type contracts](../tests/test_handler_types.py),
[writer throughput](../tests/test_writer_throughput.py),
[Requester behaviour](../tests/crawl/test_requester.py) and
[CLI header input](../tests/cli/test_request_headers.py). Keep corrections to
assertions and comments separate from file moves.

## Whole-suite review at `dc048245`

The historical Linux baseline collected 2,671 pytest cases, including
parameterized variants. The review recorded each module's scenarios, test seams,
sources of expected values, and relevant assertions or comments. Platform-specific
behavior still needs results from its native runner.

| Reviewed area | Modules | Collected cases |
|---|---:|---:|
| CLI and contract | 33 | 303 |
| Crawl | 72 | 1,603 |
| Store, fixture site and Workspace | 37 | 345 |
| Extraction, output and project-level tests | 35 | 420 |
| **Total** | **177** | **2,671** |

The Writer throughput smoke test passed when it submitted zero Pages. A
separate correction checks that the requested 105 Pages and actual Link rows
reach the Store. [Writer regression and mutation evidence](https://github.com/openlinx/openlinx/pull/63)

A Windows 3.12 run missed the start and cancellation of a 30-second probe
timer. A controlled run reproduced the failed observation when floating-point
arithmetic put the duration just above the Clock observer's 30-second limit.
[Windows job](https://github.com/openlinx/openlinx/actions/runs/44410047689/job/135175443667)

Remaining findings stay open until the original failure is demonstrated, the
reviewed fix passes the required checks and it reaches `main`. CI results belong
to the commit and platform that ran them.

After the baseline, five post-Crawl Pass cases moved from
`tests/crawl/test_hooks.py` to `tests/crawl/hooks/test_post_crawl_passes.py`
with their test names and parameter IDs preserved. [Pass test move](https://github.com/openlinx/openlinx/pull/54)

The Ruff guard in `tests/test_code_style.py` changed to check both ignore tables
for suppressed import rules. Review changed checks against their own diff.
[Ruff guard correction](https://github.com/openlinx/openlinx/pull/50) ·
[Review checklist](https://github.com/openlinx/openlinx/pull/62)

## Preparation after 022

1. Audit the resulting suite by behaviour and testing seam. Identify modules with
   mixed responsibilities before choosing directories. Start by inspecting hooks,
   writer, network-pause and code-style tests; file length is a prompt to inspect,
   not an automatic split rule.
2. Capture collected test IDs, including parameter IDs, results, coverage and the
   scenario-to-test mapping. Record platform-specific collection and results
   separately. A green run alone cannot show that moved tests remain discoverable.
3. Propose a concrete directory map and small migration slices through the
   repository's planning workflow. Preserve the useful crawl, CLI, store, extract
   and Workspace boundaries; introduce subdirectories only where they aid navigation.

## Design principles

- Group tests by stable behaviour or responsibility, not change numbers or private
  implementation structure.
- Test one behavioural rule at a time. Several assertions can describe that rule's
  outcome. Parametrize equivalent input/output variants with readable case IDs;
  keep distinct stories and failure boundaries separate.
- Share focused setup helpers while leaving meaningful inputs and literal expected
  values visible. Avoid a generic test framework or fixtures broader than needed.
- Use the narrowest agreed public seam that proves the rule. Keep wire, store and
  CLI evidence where those boundaries matter. Review apparent duplication by the
  contract it protects before proposing removal.

## Safe migration

1. Move one coherent portion per commit. Keep pure moves separate from assertion
   changes, fixture redesign and production changes.
2. Preserve scenario names, inputs, expected values, assertions, timeouts, platform
   guards and strictness. Maintain an old-to-new collected-ID manifest and account
   for every parameterized case; do not accept unexplained missing tests.
3. Run affected tests while moving, obtain independent review, then run the full
   required check before each commit. Keep platform-specific runtime verification
   where needed; static type targets do not replace it.
4. Preserve coverage thresholds and existing guards. No retries, extra skips or
   weaker assertions to make a move pass. Mutation-prove any new guard that was
   green immediately, as required by AGENTS.md.
5. Update [testing.md](testing.md) with the resulting navigation map and commands,
   and record durable rules for future agents in AGENTS.md. Verify scenario
   traceability and collected-case accounting before declaring the migration done.

Each small commit must be independently reviewable and reversible. If a move loses
cases or changes behaviour, repair that slice before continuing.
