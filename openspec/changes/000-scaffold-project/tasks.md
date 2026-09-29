Tooling change with no spec scenarios. Setup tasks name their verification. Every helper that has behaviour (CliRunner helper, home isolation, clock, fixture site) is built red → green:
1. Write the failing test at the named seam and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py` (once it exists).
4. Commit. One task = one commit, and the message names the behaviour.

Tasks marked **guard** protect later changes and pass on their first run.

## 1. Project skeleton and packaging

- [x] 1.1 Create the project files and lock:
  - `pyproject.toml`, per design D1/D2:
    - distribution `spider`, `version = "0.1.0.dev0"`
    - `requires-python = ">=3.12,<3.15"`, `license = "Apache-2.0"`, `license-files = ["LICENSE"]`, `readme = "README.md"`
    - console script `spider = "spider.cli.app:main"`
    - runtime dependency `typer`
    - `uv_build` pinned to the current minor
  - `.python-version` containing `3.12`
  - `LICENSE` with the unmodified Apache-2.0 text
  - a one-paragraph `README.md` stub
  - then run `uv lock`

  Verify: on a clean clone `uv sync --locked` succeeds, and `uv build` writes an sdist and a wheel whose `.dist-info/licenses/` contains `LICENSE`.
- [x] 1.2 Create the package:
  - `src/spider/__init__.py`, with `__version__` from `importlib.metadata` and `APP_NAME = "spider"`
  - one docstring-only `__init__.py` for each sub-package in docs/architecture.md: `cli`, `mcp`, `services`, `workspace`, `output`, `store`, `crawl`, `extract`, `rules`, `query`, `report`, `skill`. Each docstring names the change that fills the sub-package.

  Verify: `uv run python -c "import spider.cli, spider.mcp, spider.services, spider.workspace, spider.output, spider.store, spider.crawl, spider.extract, spider.rules, spider.query, spider.report, spider.skill"` exits 0.
- [x] 1.3 Drive "Checked-out text files use LF on every OS" at seam 8 (design D16).
  - **Red:** add `pytest` to the `dev` dependency group with `uv add --dev pytest` (task 3.3 configures the rest of the test stack). Then write `tests/test_line_endings.py`. It runs `git ls-files --eol` and fails on any tracked file that meets all three conditions:
    - Git detects its index content as text (`i/lf`, `i/crlf` or `i/mixed`);
    - its attributes do not include `-text`;
    - its working-tree ending is not `w/lf`.

    It selects files by content, not by the `text` attribute. Without `.gitattributes` the `attr/` column is empty, and a filter on it would pass without checking anything. On a Windows checkout with `core.autocrlf=true` and no `.gitattributes`, the test is red.
  - **Green:**
    1. Add `.gitattributes` with `* text=auto eol=lf` and `tests/fixture_site/sites/** -text` (fixture bytes stay exact).
    2. Rewrite the files that are still checked out with CRLF: delete each file that `git ls-files --eol` reports as `w/crlf` or `w/mixed`, then restore it from the index with `git checkout -- <file>`.
       - Stage any edits to those files first. The restored copy comes from the index, so an unstaged edit would be lost.
       - The files must be deleted first, because Git skips files whose stat data is unchanged.
       - `git add --renormalize .` is not enough: it rewrites only the index, and every blob is already LF.
       - A fresh clone, such as CI's, needs no second checkout.
    3. Extend `.gitignore` with `.hypothesis/` and `.coverage.*`.

  Verify: the test is green locally and on the Windows CI runner, and `git check-attr text -- tests/fixture_site/sites/basic/index.html` prints `text: unset`.
- [x] 1.4 Review: run the code-review skill on group 1's commits. Refactor with `uv sync --locked` and `uv build` still passing.

## 2. CLI skeleton and CliRunner helper (CLI seam)

This group comes before the quality gates, so that the coverage gate of task 3.3 starts with tests that import `spider`.

- [x] 2.1 Drive `spider --version` in process.
  - Red: in `tests/cli/test_version.py`, `run_cli("--version")` exits 0, and stdout is `b"spider "` + the `project.version` read from `pyproject.toml` with `tomllib` + `b"\n"`.
  - Green: `run_cli` in `tests/support/cli.py` (Typer `CliRunner`, returning `CliResult(exit_code, stdout, stderr)` as raw bytes), and `src/spider/cli/app.py` (the Typer app per design D7, with an eager `--version` and `main()`).
- [x] 2.2 Drive `spider --version` as a real process.
  - Red: `run_cli_process("--version")`, a real `python -m spider` process, returns the same stdout bytes and exit code 0 on every OS.
  - Green: the `run_cli_process` helper and `src/spider/__main__.py`.
- [x] 2.3 Guard for lazy imports (design D6): importing `spider.cli.app` in a fresh interpreter leaves none of these in `sys.modules`: `aiohttp`, `sqlalchemy`, `alembic`, `numpy`, `selectolax`, `lxml`, `pydantic`.
- [x] 2.4 Docs: add "Status" and "Development quick start" (`uv sync`, `uv run spider --version`) to `README.md`.
- [x] 2.5 Review: run the code-review skill on group 2's commits. Refactor with `uv run pytest` green; the gates arrive in group 3.

## 3. Quality gates

- [x] 3.1 Configure ruff in `pyproject.toml` per design D4: rule sets, the event-loop-policy bans, and per-file ignores for `tests/` (`S101`, `T20`, `S603`, `S607`).

  Verify:
  - `uv run ruff check .` and `uv run ruff format --check .` pass.
  - A scratch module calling `asyncio.set_event_loop_policy(None)` is reported as `TID251`. Delete the scratch module afterwards.
- [x] 3.2 Configure mypy in strict mode per design D3, over `src`, `tests` and `scripts`.

  Verify:
  - `uv run mypy` passes.
  - A scratch `def f(x): return x` in `src/spider/` is reported as untyped. Delete it afterwards.
- [x] 3.3 Configure the test stack per design D5:
  - pytest: strict markers and config, `xfail_strict`, `filterwarnings = ["error"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `timeout = 60`
  - coverage: pytest-cov + covdefaults, `source = ["spider"]`, branch, `fail_under = 90`, `patch = ["subprocess"]`
  - hypothesis profiles `dev` and `ci`, registered in `tests/conftest.py`
  - the rest of the development dependency group (`pytest` is there since task 1.3)

  Verify with two throwaway tests, deleted afterwards:
  - `async def test_tmp(): await asyncio.sleep(0)` passes without a marker.
  - A test that calls `warnings.warn("x", DeprecationWarning)` fails.
- [x] 3.4 Add `scripts/check.py` per design D11.

  Verify:
  - With every gate green it exits 0.
  - After a deliberate formatting error it exits non-zero at the `ruff format --check` step and runs no later step.
  - It behaves the same from PowerShell 5.1 and from bash.
- [x] 3.5 Docs: write the first `CONTRIBUTING.md` with "Set up" (`uv sync`) and "Checks" (`uv run scripts/check.py`, plus each gate's own command).

  Verify: every command listed runs as written on Windows and on one POSIX OS.
- [x] 3.6 Review: run the code-review skill on group 3's commits. Refactor with `uv run scripts/check.py` green.

## 4. Home isolation, temp Workspace and clock

- [ ] 4.1 Drive home isolation (autouse fixture in `tests/conftest.py` that sets `HOME` and `USERPROFILE`).
  - Red: a test that requests only `tmp_path` sees `Path.home() == tmp_path / "home"`.
  - Guard: a child process started with `sys.executable -c "import pathlib; print(pathlib.Path.home())"` prints the same folder.
- [ ] 4.2 Drive `temp_workspace`.
  - Red: inside the fixture, `Path.cwd() == temp_workspace.root` and `temp_workspace.root == tmp_path / "home" / "work"`.
  - Green: the `temp_workspace` fixture in `tests/support/workspace.py`.
- [ ] 4.3 Drive `FakeClock` time.
  - Red: `FakeClock().now()` equals `datetime(2026, 1, 1, tzinfo=UTC)`. After `advance(1.5)` it equals `datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC)`.
  - Green: the `Clock` protocol in `src/spider/clock.py` and `FakeClock` in `tests/support/clock.py`.
- [ ] 4.4 Drive `FakeClock.sleep`.
  - Red: `await FakeClock().sleep(2)` returns in under 0.1 s of real time, and afterwards `monotonic()` reads `2.0`.
  - Green: `FakeClock.sleep`.
- [ ] 4.5 Drive `SystemClock` (pure-logic seam), with two tests.
  - Red: `SystemClock().now().utcoffset()` equals `timedelta(0)`, and two consecutive `SystemClock().monotonic()` readings never decrease.
  - Green: `SystemClock`.
- [ ] 4.6 Docs: add a "Helpers" section to `docs/testing.md` covering `run_cli`, `run_cli_process`, home isolation, `temp_workspace` and `FakeClock`.
- [ ] 4.7 Review: run the code-review skill on group 4's commits. Refactor with `uv run scripts/check.py` green.

## 5. Event loop and guards

- [ ] 5.1 Drive `loop_factory` at seam 4.
  - Red: `spider.aio.loop_factory()` returns an `asyncio.ProactorEventLoop` on Windows and an `asyncio.SelectorEventLoop` elsewhere. There are two platform-specific tests, and each closes its loop.
  - Green: `src/spider/aio.py` (design D15).
- [ ] 5.2 Setup: wire `pytest_asyncio_loop_factories` in `tests/conftest.py` so that it returns only `loop_factory` (design D5).
  - **Guard:** inside an async test, `type(asyncio.get_running_loop())` is the type `loop_factory` makes on this OS.
- [ ] 5.3 Drive the network guard for sockets.
  - Red: `socket.create_connection(("93.184.216.34", 80), timeout=1)` raises `NetworkAccessBlocked`.
  - Green: the autouse guard in `tests/conftest.py`, patching `socket.socket.connect` and `connect_ex` (design D13).
- [ ] 5.4 Drive the network guard for name resolution.
  - Red: `urllib.request.urlopen("http://example.com/", timeout=1)` fails, and `NetworkAccessBlocked` is its cause.
  - Green: a patch of `socket.getaddrinfo` that allows only `localhost` and loopback addresses.
- [ ] 5.5 Drive the network guard for event-loop connections.
  - Red: in an async test, an aiohttp `GET http://93.184.216.34/` raises `aiohttp.ClientConnectorError` caused by `NetworkAccessBlocked`, on every OS.
  - Green: a patch of `sock_connect` on the loops that `loop_factory` makes. The Windows Proactor loop connects through `ConnectEx`.
- [ ] 5.6 **Guard:** loopback stays reachable. A server socket bound to `127.0.0.1:0` accepts a connection from the test.
- [ ] 5.7 Drive proxy isolation.
  - Red: a `pytester` run is started with `HTTP_PROXY` and `https_proxy` set in its environment. It runs a test that asserts that none of the proxy variables of design D13 is in `os.environ`, and that test fails.
  - Green: the autouse fixture that removes them, in the plugin `tests/support/isolation.py` loaded by `tests/conftest.py`.
  - **Guard:** a test that sets `HTTP_PROXY` with `monkeypatch.setenv` sees that value.
- [ ] 5.8 Drive the dependency allowlist.
  - Red: with an empty `tests/dependency_allowlist.txt`, the test fails and names `typer` and every dependency it pulls in, with markers evaluated for the current platform.
  - Green: list them, each with a short reason, and add `packaging` to the development group (design D14).
- [ ] 5.9 **Guard:** the telemetry and LLM denylist of design D14. The test fails if any listed package is a runtime dependency, even an allowlisted one.
- [ ] 5.10 Docs:
  - Add the network guard, the dependency allowlist and `loop_factory` to the "Helpers" section of `docs/testing.md`.
  - Add "Adding a dependency" to `CONTRIBUTING.md`: the allowlist edit belongs in the same commit.
- [ ] 5.11 Review: run the code-review skill on group 5's commits. Refactor with `uv run scripts/check.py` green.

## 6. Local fixture site (HTTP seam)

- [ ] 6.1 Drive serving a page from a file.
  - Red: site `sites/basic/` declares `Page(file="index.html")` at `/`. `GET /` returns 200, `Content-Type: text/html; charset=utf-8`, and a body equal to the file's bytes.
  - Green:
    - the route dataclasses and the extension → content-type table
    - the aiohttp app, run in a background thread and bound to `127.0.0.1:0`
    - the `fixture_site` fixture and `ServerHandle.base_url` / `url()`
- [ ] 6.2 Drive byte-exact files.
  - Red: a site file whose bytes are exactly `b"a\r\nb\nc"` is served as exactly those bytes on every OS.
  - Green: binary reads, plus the `-text` rule from task 1.3 applied to that file.
- [ ] 6.3 Drive `Status`.
  - Red (hypothesis, module-scoped server): for any status code from 200 to 599, `Status(code)` at `/s/<code>` is served with exactly that status.
  - Green: the `Status` route and the module-scoped fixture variant.
- [ ] 6.4 Drive `Redirect`.
  - Red: `Redirect("/b", status=301)` at `/a` returns 301 with `Location: /b` exactly as declared, not made absolute.
  - Green: `Redirect`.
- [ ] 6.5 Drive redirect chains and loops, with two tests.
  - Red:
    - For the chain `/r1` → `/r2` → `/r3` → `/final`, an aiohttp client records exactly 3 redirects and then status 200.
    - For the loop `/loop-a` ↔ `/loop-b`, a client with `max_redirects=10` raises `TooManyRedirects`.
  - Green: the `redirect_chain(prefix, hops, to)` helper.
- [ ] 6.6 Drive `Robots`.
  - Red: `Robots("User-agent: *\nDisallow: /private/\n")` at `/robots.txt` returns 200, `Content-Type: text/plain; charset=utf-8`, and exactly those bytes.
  - Green: `Robots`.
- [ ] 6.7 Drive `Sitemap`.
  - Red: `Sitemap(paths=["/", "/about"])` at `/sitemap.xml` returns `Content-Type: application/xml`, and a body equal to the literal `<urlset>` document whose `<loc>` values are `<base_url>/` and `<base_url>/about`.
  - Green: `Sitemap`.
- [ ] 6.8 Drive `SitemapIndex`.
  - Red: `SitemapIndex(paths=["/sitemap-1.xml"])` returns `Content-Type: application/xml` and the literal `<sitemapindex>` document, whose `<loc>` is `<base_url>/sitemap-1.xml`.
  - Green: `SitemapIndex`. Gzipped sitemap files are ordinary `Page(file=…)` routes; `022` adds gzip transfer encoding.
- [ ] 6.9 Drive custom and repeated headers.
  - Red: a route with `headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("X-Robots-Tag", "noindex"), ("Link", '<https://example.com/>; rel="canonical"')]` answers with:
    - `Set-Cookie` values `["a=1", "b=2"]`, in that order
    - `X-Robots-Tag: noindex`
    - the literal `Link` value
  - Green: the `headers` option.
- [ ] 6.10 Drive `content_type`.
  - Red: `Page(file="cp1251.html", content_type="text/html; charset=windows-1251")` is served with that exact `Content-Type`.
  - Green: the `content_type` option.
- [ ] 6.11 Drive `delay`.
  - Red: with `delay=0.5`, the response headers arrive no sooner than 0.5 s after the request, measured with `time.monotonic()`.
  - Green: the `delay` option.
- [ ] 6.12 Drive `hang`.
  - Red: with `hang=True`, a client with a 0.3 s total timeout raises `TimeoutError`. Stopping the server afterwards finishes within 2 s and raises no warning.
  - Green: the `hang` option and cancellation on shutdown.
- [ ] 6.13 Drive `LargeFile`.
  - Red: `LargeFile(size=3_000_000)` answers with `Content-Length: 3000000`, a body of 3,000,000 bytes, and a SHA-256 equal to a literal. The literal is computed once, by hand, from the documented pattern (bytes 0–255 repeated).
  - Green: `LargeFile`, as a streamed response.
- [ ] 6.14 Drive templating, with two tests.
  - Red:
    - `Page(body='<a href="{{base_url}}/about">', template=True)` is served with `{{base_url}}` replaced by `ServerHandle.base_url`.
    - The same body without `template=True` is served unchanged.
  - Green: the `template` option.
- [ ] 6.15 Drive the request log.
  - Red: after `GET /` with `User-Agent: probe/1.0` and then `HEAD /about`, `ServerHandle.requests` lists `GET /` with user agent `probe/1.0` first and `HEAD /about` second.
  - Green: the request-log middleware.
- [ ] 6.16 Guard: a separate process (`sys.executable -c` using `urllib.request`) fetches `/` from the in-test server and receives the page bytes.
- [ ] 6.17 Docs: write `tests/fixture_site/README.md`, covering declaring a site, route kinds and options, the fixtures, and the extension rule (design D9). Add the fixture site to the "Helpers" section of `docs/testing.md`.
- [ ] 6.18 Review: run the code-review skill on group 6's commits. Refactor with `uv run scripts/check.py` green.

## 7. Continuous integration

- [ ] 7.1 Add the seam 9 wiring: `tests/js/smoke.test.mjs`, a single `node:test` case, and a `node --test tests/js/` step in `scripts/check.py` that is skipped with a notice when `node` is missing (design D11).

  Verify: `node --test tests/js/` passes locally, and the check script skips the step cleanly without Node.
- [ ] 7.2 Add `.github/workflows/ci.yml` per design D10:
  - the 3 OS × 3 Python matrix
  - ruff, strict mypy and pytest with the 90% coverage gate
  - the wheel smoke test
  - Node set up, then `openspec validate --all --strict` with `OPENSPEC_TELEMETRY=0`, then `node --test tests/js/`
  - actions pinned to commit SHAs

  Verify: a push runs 9 cells, and all of them pass. The Windows cells also finish task 1.3's check: `tests/test_line_endings.py` is green on a fresh checkout with `core.autocrlf=true`.
- [ ] 7.3 Prove that the gates fail CI. On a throwaway branch, push each of the following in turn, then delete the branch:
  - a failing test
  - a change that drops coverage below 90%
  - a strict-typing error
  - an invalid OpenSpec change
  - a failing `node --test` case

  Verify: each one turns the run red.
- [ ] 7.4 Docs: add a CI badge to `README.md` and a "What CI runs" section to `CONTRIBUTING.md`.
- [ ] 7.5 Review: run the code-review skill on group 7's commits. Refactor with CI green.

## 8. Contributor documents

- [ ] 8.1 Guard: add `tests/test_docs_links.py`. It checks that every relative link in `README.md`, `CONTRIBUTING.md` and `docs/**/*.md` points to an existing file.
- [ ] 8.2 Docs: complete `CONTRIBUTING.md` with:
  - the TDD loop, linked to `docs/testing.md`: red → green, one commit per green slice naming its scenario, and a review task at the end of every task group
  - the OpenSpec workflow: `/opsx:propose` → `/opsx:apply` → `/opsx:archive`
    - Codex uses the same skills from `.agents/skills`.
    - `OPENSPEC_TELEMETRY=0` is set with `export` in bash and `$env:OPENSPEC_TELEMETRY = "0"` in PowerShell.
  - conventions: CONTEXT.md terms, ADRs, and the `spider` placeholder name
  - Windows notes: use `scripts/check.py` in PowerShell 5.1, and use `127.0.0.1`, not `localhost`, in tests

  Verify: task 8.1's test passes.
- [ ] 8.3 Docs: complete `README.md`:
  - what the tool is: an agent-first SEO crawler with no GUI
  - its status: pre-release, and the name is still open
  - links to ROADMAP.md, CONTEXT.md, docs/architecture.md, docs/adr/ and CONTRIBUTING.md
  - the license

  Verify: task 8.1's test passes.
- [ ] 8.4 Review: run the code-review skill on group 8's commits. Refactor with `uv run scripts/check.py` green.
