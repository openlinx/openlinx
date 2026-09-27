## Why

The repository holds only planning documents. Every later v0.1 change needs the same foundation: a uv-managed Python package, strict quality gates that run the same way on Windows, macOS and Linux, and a local fixture site to test crawling without the internet. The project is built test-first ([docs/testing.md](../../../docs/testing.md)), so the test tooling must exist before the first behaviour is written.

## What Changes

- **Project and packaging**
  - `pyproject.toml` built with the `uv_build` backend.
    - `requires-python = ">=3.12,<3.15"` and license `Apache-2.0`.
    - The console script `spider`.
    - PEP 735 dependency groups for development tools.
  - A committed `uv.lock` and `.python-version` (3.12, the lowest supported version).
  - The `src/spider/` package with the sub-packages listed in docs/architecture.md, plus:
    - `spider/clock.py`, an injectable clock
    - `spider/aio.py`, the project's event-loop factory: a Proactor loop on Windows, a selector loop elsewhere, never event-loop policies
    - `python -m spider`
- **CLI skeleton:** a Typer app with `spider --version` (prints `spider <version>`) and `spider --help`. No other Commands.
- **Quality gates:**
  - ruff for linting and formatting.
  - mypy in strict mode.
  - pytest with pytest-asyncio, hypothesis and pytest-timeout. Async tests run on the project's loop factory through the `pytest_asyncio_loop_factories` hook.
  - Coverage through pytest-cov that fails below **90% line + branch** on `src/`.
  - **Guards:**
    - tests may open network connections and resolve names only for loopback addresses and `localhost`
    - tests never inherit proxy variables. `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `ALL_PROXY`, in any letter case, are cleared for every test unless the test sets them itself.
    - a dependency allowlist test keeps every runtime dependency explicit, and rejects any telemetry or LLM SDK
  - `scripts/check.py` runs every gate in order with one cross-platform command. It works in PowerShell 5.1, which has no `&&`.
- **Test support shared by every later change:**
  - a CliRunner helper, for in-process runs and real subprocess runs
  - a temp-Workspace fixture that isolates the home folder and the current folder
  - `FakeClock`, a controllable implementation of the clock
  - the **local fixture site**. It is an aiohttp test server whose sites are declared as data:
    - pages served byte-for-byte from files, or inline bodies
    - any status code
    - redirects, including chains and loops
    - `robots.txt`
    - XML sitemaps and sitemap indexes
    - custom and repeated headers (`X-Robots-Tag`, `Set-Cookie`, `Link`)
    - slow responses and responses that never arrive (for timeouts)
    - large streamed files
    - `{{base_url}}` templating
    - a request log
- **CI:** a GitHub Actions workflow that runs on Windows, macOS and Linux × Python 3.12, 3.13 and 3.14.
  - Each cell runs ruff, the strict type check, the tests with the coverage gate, and a wheel build smoke test (`spider --version` from the built wheel).
  - Each cell sets up Node, then runs `openspec validate --all --strict` and `node --test tests/js/`. `tests/js/` is seam 9, the Report's table script; `070` fills it, and a smoke test proves the wiring until then.
- **Repository documents:**
  - `LICENSE` (Apache-2.0)
  - `README.md`
  - `CONTRIBUTING.md`, which covers the TDD loop (linked to docs/testing.md), the OpenSpec workflow `/opsx:propose` → `/opsx:apply` → `/opsx:archive` with `OPENSPEC_TELEMETRY=0`, and the checks
  - `.gitattributes`, which checks out every text file with LF line endings on every OS and keeps fixture files byte-exact
  - additions to `.gitignore`

**Commands and flags added:** `spider --version`, `spider --help`, `python -m spider`. No MCP tools.

## Capabilities

### New Capabilities

None. This change is tooling only, and `.openspec.yaml` sets `skip_specs: true`. The only user-facing behaviour is `spider --version`. The CLI output contract that governs every other Command is specified in `010-add-workspace-and-cli-contract`.

### Modified Capabilities

None.

## Non-goals

- The JSON output contract, errors and exit codes, the Workspace and `spider.toml` belong to `010-add-workspace-and-cli-contract` (v0.1). The crawl store belongs to `015-add-crawl-store` (v0.1).
- The crawler and its runtime dependencies (aiohttp as a runtime dependency, Protego, selectolax) belong to `020-add-crawl-core` (v0.1).
- The fixture site serves plain HTTP only. It has no HTTPS, named virtual hosts, gzip, basic auth, proxy or flaky-response sequences yet. `022-add-fetch-policy` (v0.1) adds them together with the fetching scenarios that need them. Gzipped sitemap files are served as ordinary files for `024-add-list-and-sitemap-modes` (v0.1).
- `spider doctor` belongs to `080-add-agent-skill` (v0.1).
- Installer scripts, the PyPI release pipeline and the policy for raising the Python upper bound belong to `100-add-installers` (v0.1).
- The product name is still open. The placeholder `spider` is used everywhere, and publishing is blocked until the name is chosen.

## Impact

- **New files:**
  - `pyproject.toml`, `uv.lock`, `.python-version`, `.gitattributes`
  - `src/spider/**`
  - `tests/support/**`, `tests/fixture_site/**`
  - `scripts/check.py`
  - `.github/workflows/ci.yml`
  - `LICENSE`, `README.md`, `CONTRIBUTING.md`
- **More new files:** `tests/dependency_allowlist.txt`, and `tests/js/smoke.test.mjs`.
- **Edited files:** `.gitignore`, and a short "Helpers" section in `docs/testing.md`.
- **Runtime dependency:** `typer`.
- **Development dependencies:** `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-timeout`, `pytest-cov`, `covdefaults`, `hypothesis`, `aiohttp`, `packaging`.
- **CI needs Node.js** for the pinned OpenSpec CLI and for `node --test` (seam 9). Locally, `scripts/check.py` skips both with a notice when Node is missing.
- **Every later change** builds on the package layout, the gates and the fixture site defined here.
