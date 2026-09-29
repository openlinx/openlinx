## Context

The repository is greenfield. It holds CONTEXT.md, ROADMAP.md, docs/ and the OpenSpec workspace, but no code. See proposal.md (Why) for the motivation.

These constraints are already settled elsewhere:
- **Stack and platforms:** Python `>=3.12,<3.15` on Windows, macOS and Linux; uv for environments; Typer for the CLI; pytest with a local fixture site (docs/architecture.md).
- **Test-first:** every behaviour starts as a failing test at an agreed seam. CI fails below 90% line + branch coverage on `src/`, and the type checker runs in strict mode (docs/testing.md).
- **Package layout:** `src/spider/` with the sub-packages listed in docs/architecture.md.

This change decides the tooling. It builds no product behaviour beyond `spider --version`.

## Goals / Non-Goals

**Goals:**
- One command sets up a working environment on any OS: `uv sync`.
- One cross-platform command runs every quality gate locally, and CI runs the same gates.
- Test helpers that later changes use without modification:
  - a CliRunner helper
  - a temp-Workspace fixture
  - an injectable clock with a fake
  - the local fixture site
- Placeholder names are cheap to rename once the product name is chosen.

**Non-Goals:**
- Any Command other than `--version` and `--help`.
- The JSON output contract. It comes in `010-add-workspace-and-cli-contract`, and until then `--version` is the only output.
- Fixture-site features that no scenario here needs: HTTPS, virtual hosts, gzip, auth, proxy and flaky sequences. `022-add-fetch-policy` adds them with the fetching scenarios that need them.
- Release automation and PyPI publishing (`100-add-installers`).

## Decisions

### D1. Build backend: `uv_build`

- **Why:**
  - It needs no configuration for the `src/spider/` layout.
  - It packages every file under the module root: templates, the Arial width table, rule YAML, Alembic migrations and Skill templates, with no include lists.
  - It validates PEP 639 license metadata and is maintained together with uv, which the project already requires.
- **Pin:** the current minor, as uv recommends (`uv_build>=0.12,<0.13` at the time of writing).
- **Limitations that apply to us:**
  - Pure Python only. We build no extension modules; numpy and zstd come as wheels.
  - No dynamic version plugins (see D2).
- **Alternatives:**
  - **hatchling + hatch-vcs:** mature and flexible, with versions from git tags. Rejected for now: we need no build hooks, and git-derived versions complicate builds from source archives that have no `.git`. Switching is a one-file change.
  - **setuptools + setuptools-scm:** heavier configuration and known pitfalls with package data.
  - **flit-core / pdm-backend:** fine, but each is one more tool with no advantage here.

### D2. Version: static in `pyproject.toml`, read at runtime

- `version = "0.1.0.dev0"` lives in `pyproject.toml`. It is bumped with `uv version --bump …`.
- `spider.__version__` reads it through `importlib.metadata.version("spider")`.
- `spider --version` prints exactly `spider <version>\n` as plain text and exits 0. It is one of the two documented exceptions to JSON output; `--help` is the other.
- `100-add-installers` owns the check that a release tag equals this version.
- **Alternative:** a version derived from git tags (hatch-vcs). Rejected with D1.

### D3. Type checker: mypy in strict mode

- `strict = true`, plus `warn_unreachable` and the error codes `ignore-without-code`, `redundant-expr`, `truthy-bool` and `possibly-undefined`.
- It checks `src`, `tests` and `scripts`.
- `python_version` is **not** pinned, so each CI cell checks with its own interpreter. The 3.12 cells catch APIs that exist only in 3.13 or 3.14.
- **Why mypy:**
  - It is pure Python and locked by `uv.lock`, with no Node.js runtime. It behaves the same on all three OSes and inside network-restricted agent sandboxes once `uv sync` has run.
  - Our key dependencies check their own typing with mypy: SQLAlchemy 2's typing tests, aiohttp and Typer.
  - pydantic ships a mypy plugin, which `010` enables together with pydantic-settings.
  - With per-module overrides for untyped packages (Protego, for example), strict mode stays quiet on partially typed dependencies. Pyright's `reportUnknown*` family flags every call into such packages.
- **Alternatives:**
  - **pyright / basedpyright:** faster, with better inference and parity with Pylance. Rejected as the gate for the noise and the Node runtime above. Contributors may still use Pylance locally.
  - **ty (Astral):** can be trialled later. Switching changes no spec.

### D4. Lint and format: ruff

- Ruff lints and formats the code. `line-length = 100`. The target version is taken from `requires-python`.
- **Rule sets:**

  | Rules | Why |
  |---|---|
  | `E`, `W`, `F`, `I`, `UP`, `B`, `SIM`, `C4`, `RUF`, `PT` | Baseline correctness and style |
  | `S` (bandit) | Crawled content is untrusted |
  | `ASYNC` | Blocking calls inside coroutines |
  | `PTH` | "pathlib everywhere" (architecture) |
  | `DTZ` | Timezone-aware datetimes only |
  | `T20` | No `print` in `src/`: all output goes through the output layer that `010` adds |
  | `TID251` | Bans event-loop policy APIs (below) |

- **Banned APIs:** `asyncio.set_event_loop_policy`, `asyncio.get_event_loop_policy`, `asyncio.DefaultEventLoopPolicy`, `asyncio.AbstractEventLoopPolicy` and the `Windows*EventLoopPolicy` classes. Each is banned with a message pointing to `asyncio.run(..., loop_factory=spider.aio.loop_factory)`, which the architecture requires (D15).
  - The same names are also banned where they are defined, `asyncio.events.*` and `asyncio.windows_events.*`. Otherwise an import from the submodule would get past the ban.
- **Per-file ignores in `tests/`:**
  - `S101` (assert) and `T20` (print).
  - `S603` and `S607` (subprocess calls): tests start only fixed commands of their own, such as `git ls-files` and `sys.executable -m spider`. Replacing `"git"` with `shutil.which("git")` only trades `S607` for `S603`.
- **Per-file ignores in `scripts/`:** `T20`, because the check script reports its progress with `print`, and `S603`, because it runs only its own fixed commands. It finds `openspec` with `shutil.which`, so it needs no `S607`.

### D5. Test runner, coverage and property tests

- **pytest settings:**
  - `--strict-markers` and `--strict-config`, with `xfail_strict = true`.
  - `filterwarnings = ["error"]`. Unclosed sockets, sessions and files surface as failures, and on Windows those are what later break temp-folder cleanup.
- **pytest-asyncio:**
  - `asyncio_mode = "auto"`.
  - `asyncio_default_fixture_loop_scope = "function"`.
  - The `pytest_asyncio_loop_factories` hook in `tests/conftest.py` returns only `spider.aio.loop_factory`, so every async test runs on the loop that production uses (D15). No event-loop policy is involved.
- **pytest-timeout:** `timeout = 60`. It uses the thread method automatically on Windows, where signals are unavailable, so a hung test never stalls CI.
- **Coverage** (pytest-cov over coverage.py):
  - `source = ["spider"]`, `branch = true`, `fail_under = 90`, and `patch = ["subprocess"]` so that real subprocess runs of the CLI count.
  - `covdefaults` provides platform and version pragmas, such as `# pragma: win32 cover`. Code that can only run on one OS is excluded on the others, and the 90% gate stays meaningful on every cell and on a developer's machine.
  - **Alternative:** combine coverage data from all nine cells in a final job. Rejected: the local gate would then disagree with CI.
- **hypothesis:**
  - Profiles are registered in `tests/conftest.py`: `dev` (the default) and `ci` (`deadline=None`, `print_blob=True`, `max_examples=200`).
  - CI selects `ci` through `HYPOTHESIS_PROFILE`.
  - `.hypothesis/` is git-ignored.

### D6. Package skeleton and lazy imports

- **Sub-packages up front:** every sub-package from docs/architecture.md is created now, each with a one-line docstring that names the change that fills it:
  - `cli`, `mcp`, `services`, `workspace`, `output`, `store`
  - `crawl`, `extract`, `rules`, `query`, `report`, `skill`
  - Later changes that run in parallel then add modules without colliding on `__init__.py`.
- **`src/spider/clock.py` (addition to the layout):**
  - the `Clock` protocol: `now()` returns a timezone-aware UTC `datetime`, `monotonic()` returns a `float`, and `async sleep(seconds)`
  - `SystemClock`
  - Time is a system boundary, so every component that reads it takes a `Clock`.
- **`src/spider/aio.py` (addition to the layout):** `loop_factory`, the one event-loop factory for production and tests (D15).
- **Lazy imports:**
  - Command modules import heavy libraries inside the functions that use them. This covers aiohttp, SQLAlchemy, Alembic, numpy, selectolax, lxml and pydantic.
  - This keeps `spider --version`, `--help` and `commands` fast. Agents start one process per Command.
  - A guard test fails if importing `spider.cli.app` loads any of them. The guard passes from day one; it protects the later changes.
- **Command registration:** each Command group is registered explicitly in `cli/app.py`, one line per module. It is easy to grep, and merge conflicts are trivial.

### D7. Typer skeleton

- **App settings:**
  - `pretty_exceptions_enable=False`. Rich tracebacks dump local variables, which can hold secrets such as basic-auth passwords. `010` replaces them with JSON errors.
  - `add_completion=False`. Shell-completion install options are noise for agents.
  - `no_args_is_help=True`.
- `--version` is an eager callback on the root.
- `python -m spider` runs the same app through `src/spider/__main__.py`. `060` relies on it to start detached processes with `sys.executable -m spider`.
- The placeholder name appears in `pyproject.toml` (distribution, script), in the import package, and in one constant `APP_NAME` used for user-visible strings. Renaming is then a mechanical search-and-replace plus that constant.

### D8. Test support helpers (`tests/support/`)

- **CliRunner helper.**
  - `run_cli(*args, input=None)` runs the Typer app in-process with Typer's `CliRunner`. It returns `CliResult(exit_code, stdout: bytes, stderr: bytes)`, bytes exactly as written.
  - `run_cli_process(*args, env=None)` runs `sys.executable -m spider` as a real process, for console-encoding and process tests.
    - `env` is laid over the test's own environment; it does not replace it. On Windows, a child process without `PATH` or `SYSTEMROOT` may not start. The merge is built test-first by the first test that passes `env`.
  - JSON parsing helpers are added by `010-add-workspace-and-cli-contract`, when the first JSON output exists.
- **Home isolation and the temp-Workspace fixture.**
  - An autouse fixture points `HOME` and `USERPROFILE` (what `Path.home()` reads on Windows) at `tmp_path/home`. No test can ever touch the developer's real `~/.spider/`.
  - The `temp_workspace` fixture also creates `tmp_path/home/work` and makes it the current folder. It yields `TempWorkspace(home, root)`.
  - The root sits *under* the fake home on purpose. `010`'s Workspace search stops at the home folder, so a test never climbs into the real parents of the temp folder.
- **`FakeClock`.**
  - It implements `Clock`.
  - `now()` starts at the literal `2026-01-01T00:00:00+00:00`, and `monotonic()` starts at `0.0`.
  - `advance(seconds)` moves both. `await sleep(seconds)` advances virtual time, yields once to the event loop and never waits in real time.

### D9. Local fixture site (`tests/fixture_site/`)

- **Sites are Python modules**, one folder per site: `sites/<name>/site.py` plus its page files.
  - A site is declared as data with frozen dataclasses:
    - `Site(routes={path: Route})`
    - route kinds: `Page(file=… | body=…, template=False)`, `Status(code)`, `Redirect(location, status=301)`, `Robots(text)`, `Sitemap(paths)`, `SitemapIndex(paths)`, `LargeFile(size)`
    - a gzipped sitemap file for `024` is served as an ordinary `Page(file=…, content_type="application/gzip")`
    - common options on every route: `headers=[(name, value), …]` (repeats allowed), `content_type`, `delay` (seconds before the headers), `hang` (never respond)
  - Tests may also build a `Site` inline.
  - **Alternative:** TOML or YAML site files. Rejected: they need a loader and schema validation of their own, while Python site modules are type-checked by mypy and completed by editors at no cost.
- **Byte-exact pages:**
  - Files are served as the exact bytes on disk.
  - The content type comes from a fixed internal extension table, never from `mimetypes`: on Windows, `mimetypes` reads the registry and returns different answers on different machines.
  - `.gitattributes` marks `tests/fixture_site/sites/**` as `-text`, so Git never converts line endings.
- **Templating:** a page with `template=True` has `{{base_url}}` replaced with the running server's base URL. Sitemaps always emit absolute URLs built from the base URL.
- **Server:**
  - aiohttp runs in a background thread with its own event loop, bound to `127.0.0.1` on port 0.
  - It binds loopback only, which triggers no Windows Firewall prompt, and it never uses `localhost`: on Windows `localhost` tries `::1` first, and a refused connection there costs about 2 s.
  - The same server serves in-process sync tests, async tests and subprocess tests (such as a real `spider crawl` in later changes) over TCP.
  - Shutdown cancels hanging handlers and joins the thread. With `filterwarnings = error`, a leaked socket fails the test.
- **Pytest fixtures:**
  - `fixture_site(site) -> ServerHandle` is function-scoped.
  - `ServerHandle` exposes `base_url`, `url(path)` and `requests`, a snapshot of the request log. Each entry has method, path with query, headers and a monotonic receive time.
  - A module-scoped variant exists for hypothesis tests, because hypothesis rejects function-scoped fixtures.
- **Extension rule for later changes:**
  - Add a route kind or option with a failing test in `tests/fixture_site/`, then implement it.
  - Add sites as new folders.
  - Never change the meaning of an existing option.
  - `022-add-fetch-policy` adds TLS (trustme), named virtual hosts and gzip this way.

### D10. CI (`.github/workflows/ci.yml`)

- **Triggers and settings:**
  - Push to `main`, pull requests and manual runs.
  - `permissions: contents: read`, and a concurrency group that cancels superseded runs.
  - The matrix is `os: [ubuntu-latest, macos-latest, windows-latest]` × `python: ["3.12", "3.13", "3.14"]`, with `fail-fast: false` and `timeout-minutes: 30`.
- **Steps in every cell:**
  1. `actions/checkout`, then `astral-sh/setup-uv` with `python-version: ${{ matrix.python }}` and caching.
  2. `uv sync --locked`, which fails if `uv.lock` is stale.
  3. `ruff check .`, then `ruff format --check .`.
  4. `mypy` (strict).
  5. `pytest`, including the coverage gate.
  6. `uv build`, then run `spider --version` from the built wheel in an isolated environment. This proves the packaging and entry point on each OS.
  7. `actions/setup-node` with the current LTS, then `npm install -g @fission-ai/openspec@1.13.0` (pinned).
  8. `openspec validate --all --strict`, with `OPENSPEC_TELEMETRY=0`.
  9. `node --test tests/js/` for seam 9, the Report's table script. `070` adds the real tests there, and `tests/js/smoke.test.mjs` proves the wiring until then.
- **Notes:**
  - The Node steps do not depend on Python, but the maintainer asked for every gate in every cell.
  - Third-party actions are pinned to full commit SHAs with a version comment.

### D11. Local gate runner: `scripts/check.py`

- `uv run scripts/check.py` runs the CI gates in the same order through `sys.executable -m <tool>`. It stops at the first failure with that step's exit code.
- The wheel smoke test (D10, step 6) runs only in CI. It builds artefacts and installs them into a separate environment, which is too slow for every local run.
- The OpenSpec step runs only when `openspec` is on `PATH`, and `node --test tests/js/` only when `node` is. Otherwise the script prints a notice and skips the step, as docs/testing.md allows for seam 9.
- It works in PowerShell 5.1, which has no `&&`, and in POSIX shells.
- It uses only the standard library.

### D12. `.python-version` is 3.12

- The lowest supported version is the default development interpreter.
- Code written on 3.14 can depend on lazily evaluated annotations (PEP 649). That fails on 3.12, where Typer and pydantic evaluate annotations at runtime.
- CI still covers 3.13 and 3.14, and the installers (`100`) give users 3.14.

### D13. Guard: network connections to localhost only

- **What it does:** an autouse fixture in `tests/conftest.py` blocks every attempt of the test process to reach anything but loopback. It raises `NetworkAccessBlocked`, an `OSError` subclass, so client libraries report it as an ordinary connection failure.
- **What it patches:**
  - `socket.getaddrinfo`, which allows only `localhost` and literal loopback addresses (`127.0.0.0/8`, `::1`)
  - `socket.socket.connect` and `connect_ex`
  - `sock_connect` on the loops that `spider.aio.loop_factory` makes. The Windows Proactor loop connects through `ConnectEx` and never calls `socket.connect`.
- **Why:** tests must never depend on the internet. Codex sandboxes run with the network off, and a test that reaches a real host is flaky and leaks requests.
- **What still works:** the fixture site binds `127.0.0.1`. `022`'s virtual hosts resolve through the crawler's DNS resolver hook, a listed boundary double, to `127.0.0.1`. Both pass the guard.
- **Limit:** child processes started by tests are not guarded. They are pointed at the fixture site by construction.
- **Proxy isolation:** tests must not inherit a proxy from the developer's or CI's environment, because `022` honours the standard proxy variables.
  - An autouse fixture removes `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `ALL_PROXY`, in upper and lower case, before every test.
  - A test that needs a proxy sets the variables itself with `monkeypatch.setenv`.
  - The isolation fixtures (home, proxies and the network guard) live in the pytest plugin `tests/support/isolation.py`, so a `pytester` run can load them with `-p` and prove that they work.
- **Alternative:** the pytest-socket plugin. Rejected: it does not cover `ConnectEx` on Windows, and it would add a dependency for about 40 lines of code.

### D14. Guard: the dependency allowlist

- **The allowlist:** `tests/dependency_allowlist.txt` lists every runtime dependency, one normalised name per line with a short reason.
- **The test:**
  - It walks the requirements of the installed `spider` distribution through `importlib.metadata`, evaluating markers with `packaging.markers` for the current platform.
  - It fails when a dependency is missing from the allowlist, so every new dependency is reviewed in the commit that adds it.
- **A second test rejects known telemetry and LLM SDKs outright, even when they are allowlisted.** The denylist covers `openai`, `anthropic`, `google-generativeai`, `google-genai`, `langchain*`, `litellm`, `sentry-sdk`, `posthog`, `mixpanel`, `analytics-python`, `segment-analytics-python`, `amplitude-analytics`, `opentelemetry-*`, `datadog`, `ddtrace`, `newrelic`, `rollbar`, `bugsnag` and `logfire`.
- **Why:** "no telemetry" and "the tool never calls an LLM" (ADR-0004) must be checked mechanically, including through transitive dependencies.

### D15. The event-loop factory

- **The factory:** `spider.aio.loop_factory` returns `asyncio.ProactorEventLoop()` on Windows and `asyncio.SelectorEventLoop()` elsewhere.
  - Production code (`020`) runs `asyncio.run(main, loop_factory=loop_factory)`.
  - Tests get the same loop through `pytest_asyncio_loop_factories`.
- **Why these loops:**
  - The Proactor loop is Windows' default, and it supports subprocesses, which the parse pool (`026`) and `--detach` (`060`) need.
  - Nothing may use aiodns, which requires a selector loop on Windows.
- **Why not policies:** event-loop policies are deprecated from Python 3.14, and ruff bans them (D4).

### D16. LF line endings everywhere (`.gitattributes`)

- **The rule:** `* text=auto eol=lf`, so every text file is checked out with LF on every OS, whatever the developer's `core.autocrlf` is. Windows GitHub runners set `core.autocrlf=true` by default.
- **The exception:** fixture-site files are `-text` and keep their exact bytes, because some scenarios depend on them (e.g. CRLF inside HTML, or sizes in bytes).
- **Why:**
  - `install.sh` (`100`) fails on macOS and Linux if it has CRLF endings.
  - The generated Skill (`080`) must be written with LF and compared byte for byte by the release gate.
  - Hand-written expected JSON and HTML files must compare identically on every OS.
- **Why not `eol=crlf` for `*.ps1`:** Windows PowerShell 5.1 runs LF scripts, and `install.ps1` is piped to `iex`, where line endings don't matter.
- **Guard:** task 1.3's test fails whenever a text file is checked out with CRLF, so deleting `.gitattributes` turns the Windows CI job red.

## Test seams

Seams (docs/testing.md) used by this change:
- **CLI (1):**
  - `spider --version` through `run_cli` (in-process)
  - `python -m spider --version` through `run_cli_process`
  - the wheel's console script in CI
- **HTTP (3):** the fixture site's own behaviour, observed with a plain `aiohttp.ClientSession`, and with `urllib` from a subprocess for the cross-process case.
- **Pure-logic modules (4):** `SystemClock`, `FakeClock` and `loop_factory`.
- **Install and packaging (8):** a repository artefact check. `tests/test_line_endings.py` runs `git ls-files --eol` and fails when a tracked text file is checked out without LF (D16).
- **Report script (9):** only the wiring. CI runs `node --test tests/js/`, with a smoke test until `070` adds the real tests.

Test doubles:
- **The clock (`FakeClock`)** is the only one. It is in the list of allowed boundary doubles.

Test infrastructure introduced here:
- the local fixture site, which is the server seam 3 runs against
- home and current-folder isolation
- the network guard (D13) and the dependency allowlist (D14)

None of these is a double of our code. No new seam is introduced.

## Risks / Trade-offs

- **Timing tests may flake on slow Windows runners.**
  - Fixture-site timing tests assert only lower bounds, such as "the response did not arrive before 0.5 s".
  - Client timeouts in tests are generous, and hypothesis runs with `deadline=None` on CI.
- **`filterwarnings = error` may trip on a third-party deprecation.**
  - Add a narrow ignore that names the package and links the upstream issue. Never add a blanket ignore.
- **Pragmas could hide code that is never tested.**
  - covdefaults platform pragmas are allowed only on branches that cannot run on the current OS, and the review task checks every new pragma.
- **The upper bound in `requires-python` blocks installs on Python 3.15.**
  - The bound is deliberate until the dependencies ship 3.15 wheels, and `100-add-installers` owns raising it.
- **The background server thread may leak resources on shutdown under Windows' Proactor loop.**
  - Use an explicit shutdown sequence: runner cleanup, then stopping the loop, then join.
  - A test asserts clean shutdown with warnings as errors.
- **Empty sub-packages could mislead readers.**
  - Each docstring names the change that fills it.
- **Nine CI cells, each with a Node step, cost minutes.**
  - Run caching keeps each cell short. The runs themselves are fast.
- **The network guard can miss a connection path it does not patch.**
  - Tests drive the guard with a plain socket, `urllib` and an aiohttp client on every OS, so a gap shows up as a red test on the OS where it exists.
- **Contributors without Node skip seam 9 and OpenSpec validation locally.**
  - CI always runs both, and `scripts/check.py` prints which steps it skipped.

## Open Questions

- Should the repository carry `AGENTS.md` / `CLAUDE.md` pointer files for coding agents? They would point to CONTRIBUTING and `scripts/check.py`. They are not needed for any scenario and can be added at any time.
- Should layering (`cli`/`mcp` → `services` → `store`) be enforced mechanically, for example with import-linter or per-folder ruff `banned-api`? It is deferrable until two layers exist.
- Should Dependabot or Renovate update `uv.lock` and the pinned action SHAs? This is deferrable.
- Should the fixture site get a standalone runner (`python -m tests.fixture_site serve <site>`) for manual exploration? Add it when a contributor needs it.
