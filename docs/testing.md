# Testing and TDD

This project is built test-first. Every behaviour starts as a failing test, and code is written only to make it pass. The goal is that any change or new feature can be added safely: the tests describe what the tool does, not how it does it, so the internals can be reshaped freely.

Terms follow [CONTEXT.md](../CONTEXT.md). Test names use them too ("section crawl checks outside links but does not follow them").

## The loop

1. **Pick one scenario** from the change's spec (`#### Scenario:` in `openspec/changes/<id>/specs/`).
2. **Red:** write one test at an agreed seam (below) and watch it fail for the right reason.
3. **Green:** write only enough code to pass it. Don't anticipate the next test.
4. **Run the full suite and commit.** Each green slice is one commit, and its message names the scenario. Then pick the next scenario.
5. **Review:** at the end of every task group, run the `code-review` skill on the group's commits, then refactor with the suite green. Refactoring is not part of the red → green loop.

Work in **vertical slices**, one scenario at a time from test to code. Never write all the tests first and all the code afterwards.

## Seams

A seam is a public interface where behaviour is observed without reaching inside. Tests are written only at these seams, which were agreed with the maintainer on 2026-09-27:

| # | Seam | What is tested there | How |
|---|---|---|---|
| 1 | **CLI** | Commands' JSON output, exit codes, files written, `-o`, errors | Typer `CliRunner` in-process; a few real subprocess runs per OS (Windows console encoding, `--detach`) |
| 2 | **Services and store API** | Query, Crawl and Report service behaviour shared by the CLI and MCP; the Workspace and crawl-store API (create, write, read, migrate) | Direct calls to the public service / store API with a real crawl store in a temp Workspace |
| 3 | **HTTP (local fixture site)** | Crawling: Scope, robots.txt, redirects, TLS, Resources, retries, politeness | The real crawler against a local test HTTP(S) server; aiohttp is never mocked |
| 4 | **Pure-logic modules** | URL normalisation, Scope decisions, robots directives, the `--where` language, Rule evaluation, Indexability, the Page extractor (HTML in → Page data out), content metrics (words, sentences, Flesch, pixel widths) | Table-driven tests with literal expected values; property-based tests (hypothesis) for normalisation and the `--where` parser |
| 5 | **MCP tools** | Tool listings, inputs and outputs, error mapping | An in-process MCP client session |
| 6 | **Store contract** | The public schema ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)) and the data a Crawl leaves behind | `spider schema` compared with `docs/schema.md`. **"Seam 3+6"**: crawl the fixture site, then read the documented tables through a read-only connection. `spider sql` is used only in tests about `sql` itself. |
| 7 | **Report** | Report Sections, escaping, working offline, notes merge, `report brief` | Parse the generated HTML (no browser) and check the brief's JSON |
| 8 | **Install and packaging** | One-command install on each OS; the installer's `--dry-run` plan; the `.mcpb` bundle; repository artefacts (plugin and marketplace manifests, the generated Skill copy) | Smoke tests in CI on Windows, macOS and Linux against a locally built wheel; checks on the built artefacts |
| 9 | **Report script** | The Report's inline table script (sorting, filtering) | `node --test` in CI (Node is already there for `openspec validate`); skipped locally when Node is missing |

A change's `design.md` names the seams it is tested at. Adding a new seam is a design decision recorded there and agreed with the maintainer before any test uses it.

### Boundary doubles

These fakes stand in for things outside our code. They are the only test doubles allowed:
- **Fetcher:** a fake Fetcher (for deterministic politeness, rate and retry-timing tests only)
- **Clock:** an injectable clock
- **Randomness:** an injectable random source (e.g. for crawl id collisions)
- **DNS:** a DNS resolver hook
- **Proxy:** a local test proxy
- **TLS trust:** a test CA (trustme) passed into the crawler's TLS setup, so the OS trust store is never touched
- **Processes:** the OS process-spawn call (not our own launcher function)
- **`doctor`:** network and trust-store probes

Never replace our own modules or our own CLI with a double. Installer tests use a real, locally built wheel.

## Rules

- **Test behaviour through public interfaces.** A test must survive a refactor that doesn't change behaviour.
- **Use expected values from the spec** as literals. Never recompute them the way the code does. Contract tests compare against hand-written expected JSON; never auto-accept a snapshot.
- **Mock only system boundaries:** the network outside the fixture site, the clock, randomness and, occasionally, the file system. Never mock our own modules. The Fetcher interface and an injectable clock exist so that scheduler and politeness tests can be deterministic.
- **One logical assertion per test,** with a name that says *what* happens, not *how*.
- **Cross-platform:** CI runs the whole suite on Windows, macOS and Linux × Python 3.12–3.14.

## Quality gates (CI)

- Ruff (lint and format) and the type checker in strict mode.
- pytest with coverage. CI fails below **90% line + branch coverage** on `src/`.
- `openspec validate --all --strict` for the specs.
- All of the above on Windows, macOS and Linux × Python 3.12–3.14.
