# Testing and TDD

This project is built test-first. Every behaviour starts as a failing test, and code is written only to make it pass. The goal is that any change or new feature can be added safely: the tests describe what the tool does, not how it does it, so the internals can be reshaped freely.

Terms follow [CONTEXT.md](../CONTEXT.md). Test names use them too ("section crawl checks outside links but does not follow them").

## The loop

1. **Pick one scenario** from the change's spec (`#### Scenario:` in `openspec/changes/<id>/specs/`).
2. **Red:** write one test at an agreed seam (below) and watch it fail for the right reason.
3. **Green:** write only enough code to pass it. Don't anticipate the next test.
4. **Run the full suite and commit.** Each green slice is one commit, and its message names the scenario. Then pick the next scenario.
5. **Review:** at the end of every task group, run the `code-review` skill on the group's commits, then refactor with the suite green. Refactoring is not part of the red → green loop.
6. **Check the scenarios:** before a change is done, `uv run python scripts/scenario_coverage.py openspec/changes/<id>/specs/<capability>/spec.md` lists each scenario as covered, waiting (a later version's) or missing, and any with more than one test named after it. A test is named `test_` and its scenario's title in snake case, every run of other characters one `_`, without one trailing platform tag, `(Windows)`, `(POSIX)` or `(macOS)`. It is run by hand, not by the gate.

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
| 6 | **Store contract** | The public schema ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)) and the data a Crawl leaves behind | `linx schema` compared with `docs/schema.md`. **"Seam 3+6"**: crawl the fixture site, then read the documented tables through a read-only connection. `linx sql` is used only in tests about `sql` itself. |
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
| `tests/crawl/` | 4, the crawler's pure logic, such as URL normalisation; 3 and 3+6, Crawls of the fixture site; 2, the Crawl Service, and its reporter, the warning log (`test_warning_log.py`) |
| `tests/extract/` | 4, the Page extractor and the Page handler; 3+6, Crawls of the fixture site read through the Page data tables |
| `tests/contract/` | 6, the store contract (`test_schema.py`, which reads `docs/schema.md` with `openlinx.services.schema_doc.parse_tables`), and the hand-written expected JSON of the CLI contract tests (`commands/`) |
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
- **SQLite's report of a held `-shm` file:** `SQLITE_IOERR_TRUNCATE`, which a killed writer whose process is still exiting causes on Windows only at random
- **A full disk:** a connection listener that sets SQLite's `max_page_count` a few pages above the crawl file's size when each connection opens, so SQLite itself reports `SQLITE_FULL` (`tests/support/sqlite_faults.py`)

Never replace our own modules or our own CLI with a double. Installer tests use a real, locally built wheel. The hooks and the page executor are extension points, not doubles: a test registers its own hooks, or passes its own page executor to the Crawl Service as `pages=`, as `026` plugs in its process pool.

## Rules

- **Test behaviour through public interfaces.** A test must survive a refactor that doesn't change behaviour.
- **Use expected values from the spec** as literals. Never recompute them the way the code does. Contract tests compare against hand-written expected JSON; never auto-accept a snapshot.
- **Mock only system boundaries:** the network outside the fixture site, the clock, randomness and, occasionally, the file system. Never mock our own modules. The Fetcher interface and an injectable clock exist so that scheduler and politeness tests can be deterministic.
- **One logical assertion per test,** with a name that says *what* happens, not *how*.
- **Cross-platform:** CI runs the whole suite on Windows, macOS and Linux × Python 3.12–3.14.

## Helpers

Shared test code lives in `tests/support/`. `tests/` is a package, so tests import helpers as `from tests.support.cli import run_cli`.

- **`run_cli(*args, input=None, app=None)`** (`tests/support/cli.py`): runs the Typer app in process with Typer's `CliRunner`: `build_app()`, or the `app` given. It returns `CliResult(exit_code, stdout, stderr)`, where stdout and stderr are the bytes exactly as written. `result.json()` parses stdout as one JSON document, `result.stderr_json_lines()` parses each line of stderr as JSON, `result.errors()` keeps the lines that are error diagnostics, and `result.stray_stderr_lines()` the lines that are neither an event nor a diagnostic.
- **`run_cli_process(*args, env=None, timeout=None)`** (same module): runs `python -m openlinx` as a real process, through `python_command`, and returns the same `CliResult`; it fails after `PROCESS_TIMEOUT` seconds, or `timeout`, such as `CRAWL_PROCESS_TIMEOUT` for a Crawl. Use it for console encoding, line endings on pipes and process behaviour; use `run_cli` for everything else. Coverage counts these runs too.
- **`start_cli_process(*args)`** (same module): starts `linx` as a real process in the current folder, with stdout and stderr piped, for the interrupt scenarios: the test signals it once the fixture site's request log shows what it waits for. It starts Python with `python_command`, and a watchdog kills it after `CRAWL_PROCESS_TIMEOUT` (45 s). `await_event(process, name)` reads its stderr up to the event and returns its data, such as `crawl_started`'s `crawl_file`.
- **`run_example_process(*args)`** and **`start_example_process(*args)`** (same module): run the fixture app as a real process, the first to completion, the second as a `Popen` with stdin, stdout and stderr piped, for handshakes such as "write a line to stdin once a warning is read". Both stop at `PROCESS_TIMEOUT` (10 s): `start_example_process` arms a watchdog that kills the process, so a line that never comes fails the test instead of hanging CI. Both start Python with `python_command`, so the kill reaches the Command itself, not a venv launcher. A handshake reads what it waits for; it never sleeps a fixed time.
- **Isolation plugin** (`tests/support/isolation.py`, loaded by `tests/conftest.py`): three autouse fixtures that every test gets, listed below. A `pytester` run loads them with `-p tests.support.isolation`.
- **Home isolation** (`isolated_home`): every test runs with `HOME` and `USERPROFILE` pointing at `tmp_path / "home"`, so `Path.home()` never reaches the real `~/.openlinx/`. Child processes that inherit the environment see the same home. Git sees it too and runs without the developer's global `.gitconfig`, so a test that runs git passes what it needs with `-c`, as `tests/test_line_endings.py` does for `safe.directory`. Request `isolated_home` if a test needs the path.
- **Network guard** (`network_guard`, logic in `tests/support/network.py`): a test may reach only loopback.
  - `socket.getaddrinfo`, `gethostbyname` and `gethostbyname_ex` resolve only `localhost` and loopback literals.
  - `socket.socket.connect` / `connect_ex` and `sock_connect` on the `loop_factory` loop refuse any other address. The Windows Proactor loop connects through `ConnectEx`, past `socket.connect`.
  - Anything else raises `NetworkAccessBlocked`, an `OSError`, so clients report an ordinary connection failure.
  - Use `127.0.0.1`, not a real host. Child processes are not guarded, and neither is UDP `sendto`.
- **Proxy isolation** (`no_proxy_from_the_environment`): `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `ALL_PROXY`, in both cases, are removed before every test. A test that needs a proxy sets them with `monkeypatch.setenv`.
- **`loop_factory`** (`openlinx.aio`): every async test runs on the loop it makes (Proactor on Windows, Selector elsewhere), through the `pytest_asyncio_loop_factories` hook in `tests/conftest.py`. No test sets an event-loop policy; ruff bans them.
- **Fixture site** (`tests/fixture_site/`, see its [README](../tests/fixture_site/README.md)): the local HTTP server that tests crawl, at seam 3.
  - A site is data: a `Site` maps request paths to routes, such as `Page`, `Redirect` and `Robots`.
  - `server = fixture_site(site)` starts it on `127.0.0.1`, on a given port with `fixture_site(site, port=port)`, such as one where a failed Crawl found nothing listening, and returns a `ServerHandle` with `base_url`, `url(path)` and the request log. `module_fixture_site` is the variant for hypothesis tests.
  - `hosts = fixture_hosts(site, other)` starts two instances for multi-host Crawls: `site.test` and `www.site.test` name the first, `other.test` the second, through `hosts.resolver`, the DNS resolver hook; every other name fails as a DNS error.
- **Dependency allowlist** (`tests/dependency_allowlist.txt`, checked by `tests/test_dependencies.py`): every runtime dependency, transitive ones included, with a reason. A second test fails on any telemetry or LLM SDK, allowlisted or not.
- **`temp_workspace`** (`tests/support/workspace.py`): creates `tmp_path / "home" / "work"`, makes it the current folder and returns `TempWorkspace(home, root)`. The root sits under the fake home, where the Workspace search stops.
- **The fixture app** (`tests/support/app.py`, design D8 of 010): `example_app()` is `build_app(extra=AppExtra(...))` with what the contract scenarios register, the settings tables `example` (`ExampleSettings`, with `level` and the unset `token`) and the keyed `groups` (`GroupsTable`, entries with a `level`), both in `tests/support/settings.py` and registered by their references `EXAMPLE_TABLE` and `GROUPS_TABLE`, so `--help` never loads them, and, through `AppExtra(commands=...)`, the contract fixture Commands: `example-list` (the example list Command of the cli-contract spec, with `--odd`), `example-long-list` (items `n=1` to `n=60`), `example-rows` (rows `n=1`, `n=2`), `example-rows-waiting`, which holds its second row until a line arrives on stdin, so a real-process test can prove rows are flushed one by one, `example-rows-interrupted` (a row, then Ctrl+C), `example-needs-argument <name>`, `example-progress` (two progress events), `example-mixed` (an event, a warning, an event), `example-warn-and-wait` (a warning, then a wait for a line on stdin), `example-failed-outcome` (a partial result with exit code 1), `example-raises` (`RuntimeError("disk exploded")`), `example-warning-inside` (a warning inside its result), `example-interrupted` (Ctrl+C), `example-aborted` (Click's `Abort`) and `example-read-crawl`, which takes `--workspace` and `--crawl` and reports the id of the Crawl it read, as `050`'s Commands will. The fixture app's own codes, such as `example_failed`, are declared in `tests/support/app.py`, so the real tool never lists them. Each call builds a fresh app with its own registry, so nothing leaks between tests. Pass it as `run_cli(..., app=example_app())`. `settings_tables(app)` (same module) gives the settings tables an app registered, for seam-2 calls of a service that takes them.
- **`crawled(*args)`** (`tests/support/crawling.py`): runs `linx crawl` with `args` through `run_cli` and returns the path of the crawl file its result names, failing with the exit code and stderr when the Command does not exit 0. Seam 3+6 tests then read the file with `query` and `crawl_row`.
- **`crawl_result(seed, hooks=None, *, resolver=None, pages=None, reporter=None, clock=None, fetcher=None, stop=None, **crawl)`** (same module): crawls through the Crawl Service instead, which alone takes test hooks, the DNS resolver hook, a page executor (`pages`, a function that builds one), a reporter, a `FakeClock`, a fake Fetcher and the `StopSignal` that `060`'s stop request sets, with `crawl` as settings of the `[crawl]` table, and returns its `CrawlResult`.
- **`continued(crawl, overrides=None, hooks=None, *, resolver=None, reporter=None, clock=None, fetcher=None, stop=None)`** (same module): continues the Crawl that a `CrawlResult` ended through the Crawl Service, as `060`'s resume does, with `CrawlOverrides` for the settings a resume may change, and returns the continue's `CrawlResult`.
- **`stopped_with_an_error()`** (same module): a Crawl that its URL limit stopped after one URL got no response, as a continue finds it, for the units a continue runs.
- **`page_row(html, content_type=..., content_area=..., headers=..., url=...)`** (`tests/support/page_data.py`): the Page row of an analysed Page at `url` with this body and these response headers besides its Content-Type, with the Links the crawl engine gives it, through page preparation with the built-in extractors, the Page extractor's config being `content_area` when it is given, and then the Page handler, so a seam-4 test of a Page data column checks the decoding, the extractor and the handler's mapping at once. It fails on an `extractor_error`. `page_link_rows(html, headers=..., url=...)` gives the same Page's Link rows, through the `links` handler. `response_link_rows(content_type, headers=..., url=...)` gives the Link rows of an in-Scope 200 response that is not HTML, such as a PDF, built as the crawl engine builds its result: its header Links, and no extractor output.
- **`page_links(body, content_type, url, follow_nofollow=False)`** (`tests/support/pages.py`): the Links of a document, as page preparation reads them from a 200 response with the URL's own Scope, for the link extractor's seam-4 tests.
- **`BackloggedPool(backlog)`** (same module): a page executor that may hold `backlog` Pages beyond the requests in flight, as `026`'s pool does; politeness tests that must see the global cap pass it as `pages=`, since without a backlog the task bound equals the cap and hides it.
- **Shared fixture sites** (`tests/support/sites.py`): sites that several test modules crawl, named after the spec's examples, such as `NINE_PAGES`, where `/` links to `/p1` to `/p9`.
- **`closed_port()`** (`tests/support/network.py`): a loopback port that nothing listens on when it returns, for a refused connection, or for a site a test starts there later.
- **`disk_full_after(pages=n)`** (`tests/support/sqlite_faults.py`): the full-disk double above, as a context manager: SQLite reports `SQLITE_FULL` once the crawl file grows `n` pages.
- **`FakeClock`** (`tests/support/clock.py`): implements `openlinx.clock.Clock`.
  - `now()` starts at `2026-01-01T00:00:00+00:00`, or at the `start` given, as in `FakeClock(start=datetime(2026, 9, 27, 14, 3, 12, tzinfo=UTC))`. `monotonic()` starts at `0.0`.
  - `advance(seconds)` moves both, and wakes the sleeps that are due.
  - `await sleep(seconds)` waits until virtual time reaches its wake time, with no real wait. Time jumps to the earliest wake once nothing else can run: no clock call in 100 turns of the loop in a row, and no `off_loop()` hold open. So two sleeps at once move the clock once, as two hosts' rate waits do.
  - It models the event loop and the writer thread, never real I/O, which makes no clock call: a test with the fixture site or the aiohttp Fetcher uses `SystemClock`, and `tests/test_code_style.py` names a `FakeClock` beside either.
  - `off_loop()` is held while the loop waits for work on another thread that finishes without clock time, such as a writer unit (design D7 of 020).

  Production code takes a `Clock`, which is `SystemClock` outside tests.
- **Politeness timing** (the hosts' slots, the global cap, the rate turn, the task bound) is tested through the Crawl Service with `FakeFetcher` and `FakeClock`, never on the Requester's parts: `crawl_result(seed, clock=clock, fetcher=fetcher)`, with a page executor of the test's own (`pages=`) for the task bound.
- **`FakeFetcher(clock, pages, outages=(), on_start=None, on_answer=None)`** (`tests/support/fetcher.py`): the fake Fetcher, for timing scenarios only. Pass it with its `FakeClock`: `crawl_result(seed, clock=clock, fetcher=fetcher)`.
  - It answers from `pages`, keyed by the whole URL or else by path, so one host can differ from the others, and 404 for any other URL. A `FakePage(body, content_type="text/html", delay=0.0, fails=None, until=None)` answers after `delay` seconds on the clock.
  - No HTTP response: a page with `fails`, a `fetch_error` such as `"connection_error"`, gets none until the clock's `monotonic()` reaches `until`, or ever when `until` is `None`, as a dead section does. `outages`, spans of `monotonic()` time such as `[(1, 30)]`, fail every request that starts in them, whatever its URL, as a network that is down does. A failure takes the page's delay too, as a connection that times out does.
  - `on_start` maps a whole URL or a path to a callback that runs when its request starts, such as `lambda: stop.set("interrupt")`, which stops the Crawl at that point as an interrupt or a stop request would.
  - `starts` holds each request's whole URL and the `monotonic()` at which it started, and `path_starts` the same by path, for a test of one host. `most_in_flight` is the most requests in flight at once.
  - A test of the network pause's count needs failures that end one by one, from URLs that are requested. While paused, the URLs of an origin whose robots.txt failed wait at the pause's gate, and when a dead section ends it they are all recorded at once from the kept verdict.
- **Crawls** (`tests/support/crawls.py`): `new_crawl(workspace)` is a `NewCrawl` request for any Spider-mode Crawl with no secrets, for tests whose scenario does not name its metadata; pass it to `openlinx.services.crawls.create_crawl`. `create_any_crawl(temp_workspace, **changes)` creates one, with `changes` to the request, at `STARTED_AT` (`2026-09-27T14:03:12.345Z`, the spec's example) in the Workspace of the current folder. `create_crawl_at(temp_workspace, started_at, suffix)` creates one started at an ISO time, such as `"2026-09-27T10:00:00.000Z"`, whose id ends with `suffix`. `crawl_without_seeds(temp_workspace)` creates one whose `seeds` table is empty, for scenarios that fill it themselves. `crawl_row(file)` reads the `crawl` row as SQLite stores it, and `query(file, sql, params=())` any rows, with `?` parameters, both through a read-only connection.
- **`indexed_rows_declared()`** (`tests/support/schema.py`): a context manager that declares the public table `indexed_rows` the way `020`'s `urls` will be, with a reference to its own `id`, a unique index and a partial one, and removes it from the declaration afterwards. A Crawl created inside it has the table too, so `linx schema` and the file check see a reference and indexes before any real table has them.
- **`replay_now(writer)`** (`tests/support/writer.py`): makes a `CrawlWriter` run every unit since its last commit again, as a failing unit does, and commit them. A change that adds units calls it after running them, so its own tests check that each unit runs again the same: if one does not, `replay_now` raises `CrawlWriterClosedError` caused by a `CrawlWriterReplayError` that names the unit. `executing(statement)` (same module) is a unit that runs one statement and returns `None`, since units return values, never SQLAlchemy's result.
- **`StoreWorker(crawl_file)`** (`tests/support/store_worker.py`): a `CrawlWriter` in its own process, for the durability scenarios. `insert(*positions)` runs one unit per Seed, `flush()` flushes, and `lock()` holds `BEGIN EXCLUSIVE` on a second connection until the worker dies, which shuts readers out only in rollback-journal mode. Each call returns only when the worker has answered, so a test never sleeps, and each answer has its own `PROCESS_TIMEOUT` watchdog. Its clock is a frozen `FakeClock`, so only a flush or the 500th unit commits. `kill()` kills it (SIGKILL on POSIX, TerminateProcess on Windows), and `pid`, which the worker reports itself, is the process that `kill()` reaches. Use it as a context manager: it kills the worker on the way out, even when the test fails.
- **`python_command(*args)`** (`tests/support/processes.py`): the argv and environment that run `python *args` as a process a test can kill. On Windows a venv's `python.exe` is a launcher that runs Python as its child, so a kill would reach only the launcher; there it runs the venv's base interpreter in the venv instead, as the stdlib's multiprocessing does.
- **`slow` marker:** a test that waits real seconds or starts a real process, such as the store worker tests and the 5 s busy read. Nothing deselects it yet; `pytest -m "not slow"` skips them locally.
- **`unwritable_folder(folder)`** (`tests/support/permissions.py`): a context manager under which no file can be created in a real folder: its mode is `0o555` on POSIX, and a deny entry for Everyone is added with `icacls` on Windows, where the read-only attribute does not protect a folder. It restores the folder afterwards, and skips the test when it runs as root. `read_only_file(file)` in the same module sets a file's real read-only attribute (no write permission on POSIX) and restores it.
- **`shm_held(monkeypatch, opens)`** (`tests/support/sqlite_faults.py`): the next `opens` SQLite connections (every one for `None`) fail on their first statement with `SQLITE_IOERR_TRUNCATE`, as SQLite 3.50+ does on Windows while a killed writer that is still exiting holds `-shm`. It replaces `sqlite3.connect`, so create the Crawl before calling it.
- **`scripted_choice(characters)`** (`tests/support/randomness.py`): the random-source double. It stands in for `secrets.choice`, and each call returns the next of `characters`, so `scripted_choice("k3f9")` makes the crawl id suffix `k3f9`.

## Quality gates (CI)

- Ruff (lint and format) and the type checker in strict mode.
- pytest with coverage. CI fails below **90% line + branch coverage** on `src/`.
- `openspec validate --all --strict` for the specs.
- All of the above on Windows, macOS and Linux × Python 3.12–3.14.
