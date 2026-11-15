# Test organization plan

Status: deferred. The direction is agreed; the directory map and migration slices
still need review. Resume 022 first. Do not start this reorganization during the
current pause or alongside unfinished fetch-policy implementation.

The goal is to make tests easy to find and understand while preserving every
existing contract and regression guard. Keep the public seams and boundary doubles
in [testing.md](testing.md). TDD's refactoring step includes test clarity; it does
not require one directory per change, one test per private function, or one assertion
per test.

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
