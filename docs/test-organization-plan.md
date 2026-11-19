# Comment review and test quality plan

Status: review preparation is active; implementation follows 022. Comment review,
test quality review and test organization are separate work items. The directory
map and migration slices still need review. Do not reorganize tests alongside
unfinished fetch-policy implementation.

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

The comment sample found no actionable defect; preserve the explanations of
handler type checking and writer savepoint cost. Complete the wider review before
claiming the comment policy is satisfied throughout the repository. Keep the
documented SQL-batching and replay tests: [testing.md](testing.md) explicitly permits
those narrow checks of implementation behaviour.

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
