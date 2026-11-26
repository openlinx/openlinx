## What and why

<!-- One paragraph. For an OpenSpec change: its id and the task group. For a small fix: the scenario or doc it violated. -->

## Checklist

- [ ] `uv run scripts/check.py` ends with "All checks passed." locally, and CI is green on every OS
- [ ] Every new behaviour has a test at an agreed seam (docs/testing.md), named after its scenario, that failed before the code
- [ ] A reviewer checked each changed test against the contract at its seam, including its expected values, boundary doubles and parameterized cases. Moved tests retain their collected cases.
- [ ] Changed comments explain a current decision, invariant or non-obvious reason.
- [ ] Docs updated in the same pull request: `docs/schema.md` for tables and columns, and the area's doc for new codes, settings, options or Commands
- [ ] Terms are CONTEXT.md's, and no decision with an ADR is reopened
- [ ] Commits follow CONTRIBUTING.md: one green slice each, no attribution trailers, no competitor names except Screaming Frog
