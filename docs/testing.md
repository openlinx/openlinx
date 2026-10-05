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

### Where tests live

| Folder | Seam |
|---|---|
| `tests/cli/` | 1, CLI |
| `tests/workspace/`, `tests/store/` | 2, the Workspace and its service, and the crawl-store API; 4, the store's pure logic, such as crawl ids |
| `tests/output/` | 4, the output layer's pure logic |
| `tests/contract/` | 6, the store contract (`test_schema.py`, with its parser of `docs/schema.md`), and the hand-written expected JSON of the CLI contract tests (`commands/`) |
| `tests/js/` | 9, the Report script |
| `tests/` | the repository's own guards: dependencies, naming, line endings, docs links, isolation |

Shared helpers are in `tests/support/` and the fixture site in `tests/fixture_site/` (see [Helpers](#helpers)).

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

## Helpers

Shared test code lives in `tests/support/`. `tests/` is a package, so tests import helpers as `from tests.support.cli import run_cli`.

- **`run_cli(*args, input=None, app=None)`** (`tests/support/cli.py`): runs the Typer app in process with Typer's `CliRunner`: `build_app()`, or the `app` given. It returns `CliResult(exit_code, stdout, stderr)`, where stdout and stderr are the bytes exactly as written. `result.json()` parses stdout as one JSON document, and `result.stderr_json_lines()` parses each line of stderr as JSON.
- **`run_cli_process(*args, env=None)`** (same module): runs `sys.executable -m spider` as a real process and returns the same `CliResult`. Use it for console encoding, line endings on pipes and process behaviour; use `run_cli` for everything else. Coverage counts these runs too.
- **`run_example_process(*args)`** and **`start_example_process(*args)`** (same module): run the fixture app as a real process, the first to completion, the second as a `Popen` with stdin, stdout and stderr piped, for handshakes such as "write a line to stdin once a warning is read". Both stop at `PROCESS_TIMEOUT` (10 s): `start_example_process` arms a watchdog that kills the process, so a line that never comes fails the test instead of hanging CI. A handshake reads what it waits for; it never sleeps a fixed time.
- **Isolation plugin** (`tests/support/isolation.py`, loaded by `tests/conftest.py`): three autouse fixtures that every test gets, listed below. A `pytester` run loads them with `-p tests.support.isolation`.
- **Home isolation** (`isolated_home`): every test runs with `HOME` and `USERPROFILE` pointing at `tmp_path / "home"`, so `Path.home()` never reaches the real `~/.spider/`. Child processes that inherit the environment see the same home. Git sees it too and runs without the developer's global `.gitconfig`, so a test that runs git passes what it needs with `-c`, as `tests/test_line_endings.py` does for `safe.directory`. Request `isolated_home` if a test needs the path.
- **Network guard** (`network_guard`, logic in `tests/support/network.py`): a test may reach only loopback.
  - `socket.getaddrinfo`, `gethostbyname` and `gethostbyname_ex` resolve only `localhost` and loopback literals.
  - `socket.socket.connect` / `connect_ex` and `sock_connect` on the `loop_factory` loop refuse any other address. The Windows Proactor loop connects through `ConnectEx`, past `socket.connect`.
  - Anything else raises `NetworkAccessBlocked`, an `OSError`, so clients report an ordinary connection failure.
  - Use `127.0.0.1`, not a real host. Child processes are not guarded, and neither is UDP `sendto`.
- **Proxy isolation** (`no_proxy_from_the_environment`): `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `ALL_PROXY`, in both cases, are removed before every test. A test that needs a proxy sets them with `monkeypatch.setenv`.
- **`loop_factory`** (`spider.aio`): every async test runs on the loop it makes (Proactor on Windows, Selector elsewhere), through the `pytest_asyncio_loop_factories` hook in `tests/conftest.py`. No test sets an event-loop policy; ruff bans them.
- **Fixture site** (`tests/fixture_site/`, see its [README](../tests/fixture_site/README.md)): the local HTTP server that tests crawl, at seam 3.
  - A site is data: a `Site` maps request paths to routes, such as `Page`, `Redirect` and `Robots`.
  - `server = fixture_site(site)` starts it on `127.0.0.1` and returns a `ServerHandle` with `base_url`, `url(path)` and the request log. `module_fixture_site` is the variant for hypothesis tests.
- **Dependency allowlist** (`tests/dependency_allowlist.txt`, checked by `tests/test_dependencies.py`): every runtime dependency, transitive ones included, with a reason. A second test fails on any telemetry or LLM SDK, allowlisted or not.
- **`temp_workspace`** (`tests/support/workspace.py`): creates `tmp_path / "home" / "work"`, makes it the current folder and returns `TempWorkspace(home, root)`. The root sits under the fake home, where the Workspace search stops.
- **The fixture app** (`tests/support/app.py`, design D8 of 010): `example_app()` is `build_app(extra=AppExtra(...))` with what the contract scenarios register, the settings tables `example` (`ExampleSettings`, with `level` and the unset `token`) and the keyed `groups` (`GroupsTable`, entries with a `level`), both in `tests/support/settings.py` and registered by their references `EXAMPLE_TABLE` and `GROUPS_TABLE`, so `--help` never loads them, and, through `AppExtra(commands=...)`, the contract fixture Commands: `example-list` (the example list Command of the cli-contract spec, with `--odd`), `example-long-list` (items `n=1` to `n=60`), `example-rows` (rows `n=1`, `n=2`), `example-rows-waiting`, which holds its second row until a line arrives on stdin, so a real-process test can prove rows are flushed one by one, `example-rows-interrupted` (a row, then Ctrl+C), `example-needs-argument <name>`, `example-progress` (two progress events), `example-mixed` (an event, a warning, an event), `example-warn-and-wait` (a warning, then a wait for a line on stdin), `example-failed-outcome` (a partial result with exit code 1), `example-raises` (`RuntimeError("disk exploded")`), `example-warning-inside` (a warning inside its result), `example-interrupted` (Ctrl+C) and `example-aborted` (Click's `Abort`). The fixture app's own codes, such as `example_failed`, are declared in `tests/support/app.py`, so the real tool never lists them. Each call builds a fresh app with its own registry, so nothing leaks between tests. Pass it as `run_cli(..., app=example_app())`.
- **`FakeClock`** (`tests/support/clock.py`): implements `spider.clock.Clock`.
  - `now()` starts at `2026-01-01T00:00:00+00:00`, or at the `start` given, as in `FakeClock(start=datetime(2026, 9, 27, 14, 3, 12, tzinfo=UTC))`. `monotonic()` starts at `0.0`.
  - `advance(seconds)` moves both.
  - `await sleep(seconds)` advances virtual time and yields once to the event loop, with no real wait.

  Production code takes a `Clock`, which is `SystemClock` outside tests.
- **Crawls** (`tests/support/crawls.py`): `new_crawl(workspace)` is a `NewCrawl` request for any Spider-mode Crawl, for tests whose scenario does not name its metadata; pass it to `spider.services.crawls.create_crawl`. `crawl_row(file)` reads the `crawl` row as SQLite stores it, and `query(file, sql)` any rows, both through a read-only connection. `run_unit(file, unit)` runs one unit of work, such as `spider.store.crawls.set_state`, in its own committed transaction; it stands in only until the writer of group 4 of 015 runs units.
- **`unwritable_folder(folder)`** (`tests/support/permissions.py`): a context manager under which no file can be created in a real folder: its mode is `0o555` on POSIX, and a deny entry for Everyone is added with `icacls` on Windows, where the read-only attribute does not protect a folder. It restores the folder afterwards, and skips the test when it runs as root.
- **`scripted_choice(characters)`** (`tests/support/randomness.py`): the random-source double. It stands in for `secrets.choice`, and each call returns the next of `characters`, so `scripted_choice("k3f9")` makes the crawl id suffix `k3f9`.

## Quality gates (CI)

- Ruff (lint and format) and the type checker in strict mode.
- pytest with coverage. CI fails below **90% line + branch coverage** on `src/`.
- `openspec validate --all --strict` for the specs.
- All of the above on Windows, macOS and Linux × Python 3.12–3.14.
