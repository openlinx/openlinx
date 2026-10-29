# Architecture

A short map for contributors and coding agents. Terms follow [CONTEXT.md](../CONTEXT.md), decisions are in [adr/](adr/), and which change builds what is in [ROADMAP.md](../ROADMAP.md).

## Shape

```
        AI agents (Skill)        Claude Desktop, Codex, IDEs      people
               │                          │                         │
         ┌─────▼──────┐            ┌──────▼──────┐                  │
         │  CLI       │            │ MCP server  │                  │
         │  (Typer)   │            │ (stdio)     │                  │
         └─────┬──────┘            └──────┬──────┘                  │
               └──────────────┬───────────┘                         │
        ┌─────────────────────▼──────────────────────┐              │
        │ Services: Query · Crawl · Report            │──── HTML Report
        └─────────────────────┬──────────────────────┘
                     ┌────────▼────────┐
                     │  Crawl Store    │  one SQLite file per Crawl,
                     │  (Workspace)    │  public versioned schema
                     └─────────────────┘
```

- **The CLI and the MCP server are thin.** They parse input, call a service and serialise the result (JSON by default). Neither holds business logic, so a future REST API or web UI can wrap the same services.
- **The services are plain Python** with typed inputs and outputs.
  - The **Query Service** handles summary, pages, page, issues, sql, export and Segments.
  - The **Crawl Service** handles start, detach, status, stop, resume and dry-run.
  - The **Report Service** handles the ReportModel, HTML and Section Briefs.
- **The tool never calls an LLM** ([ADR-0004](adr/0004-tool-never-calls-an-llm.md)).

## Commands, services and output

- **A Command is an adapter plus a service.** The adapter turns flags into a typed request, picks the Reporter, calls the service and returns its result. The service holds the logic: plain Python with typed inputs and outputs, and no Click, Typer or `Output`. `spider init` is the adapter of `spider.services.workspace.init_workspace`. The MCP server (`090`) calls the same services directly and never invokes a Click Command.
- **The Reporter** (`spider.output.reporter`) is how a service reports warnings and progress events: `warn(diagnostic)` and `event(name, **data)`.
  - `CliReporter` writes each call to stderr as one JSON line.
  - `Collected` keeps the calls in memory, so the MCP server can put the warnings into a tool result.
- **The output layer** (`spider.output`) is the only code that writes. The runner builds one `Output` from the process's byte streams per invocation.
  - stdout carries only the result: a document or a list is written when the Command ends, rows are written one by one.
  - Every stderr line, a diagnostic or an event, is written under a lock and flushed at once.
  - ruff bans `print`, `sys.stdout`, `sys.stderr` and the echo functions everywhere else.
- **The error-code registry:** every diagnostic code is one `DiagnosticCode` constant in `spider.output.codes`, with its level, exit code and description, and no code is declared anywhere else in `src/`. `SpiderError` takes such a constant, never a loose string. `spider commands` lists the codes and the exit codes from it, and the MCP server maps errors from it.
- **The startup allowlist:** `spider --help` and `spider commands` may load only the standard library, Typer and its own dependencies (not rich: Typer's rich help is off), orjson and `spider`. A test checks it in a fresh process, so a new dependency must be allowed or imported lazily. pydantic, rich and every settings table load only in the Commands that need them.
- **Typer's vendored Click** (`typer._click`) is imported only in `spider.cli.click_compat`, and `typer` is pinned below the next minor version, so an upgrade touches one module and one pin.
- **The product name** is still open: every name-derived string in `src/` (the command name, the settings file, the data folder) comes from `spider.naming`.

## Settings

Settings come only from a Command's flag, then the Workspace's `spider.toml`, then the default. Each change registers its own tables:
- **Ownership:** one table has one owning change, the one that registers it. A later change adds fields to that table's model and never registers a second table for the same concern.
- **Lazy references:** a table is registered in `build_app` by its `"module:Class"` reference and imported only when settings load or the template is written, so `--help` loads no table and no pydantic.
- **Table rules,** checked by a test on every registered table, because the commented template and the error hints rely on them:
  - `extra="forbid"`, and a one-line description on every setting
  - a default TOML can write: a string, a finite number, a boolean or a list of those
  - or a `None` default for a setting that is unset; the template writes it as `# <key> =`
  - flat tables, except keyed tables
- **Keyed tables:** a table may be `dict[str, V]`, where V is a table model with a one-line docstring, for entries the user names, such as `[rules.<id>]`. Entries that are TOML literals (`050`'s `[segments]`) wait for the change that needs them, which also decides how the template describes them. The template writes the entry docstring and a commented `# [<table>.<name>]` header.
- **Secrets** are declared once, on the settings field (`json_schema_extra={"secret": True}`). An option mapped to that setting inherits it, so `spider commands` reads the table's model; an option with no setting declares `secret` itself. A test checks that every option's setting names a setting of a registered table.

## Crawl pipeline

```
Frontier ──► Engine ──► Requester ──► Fetcher ──► Page executor ──► Writer ──► Crawl Store
(urls        Scope,     host slot,    aiohttp     selectolax,       one unit per
 table)      robots,    global cap,   behind a    extractors,       URL with its
             depth      URL limit     Protocol    026's pool        handlers' rows;
                                                                    then the passes
```

- **Frontier:** the queue of URLs still to crawl lives in the crawl store, which makes it the single source of truth for resume, `status` and queries during a crawl ([ADR-0001](adr/0001-own-asyncio-engine-over-scrapy.md)).
- **Engine:** reads the frontier depth by depth and decides each URL once, at dispatch: the Scope (URLs outside it are status-checked but not followed), robots.txt (Protego, through the robots.txt loader), the depth limit and the URL limit.
- **Requester:** makes every request of a Crawl, a URL's own and robots.txt's: the host's slot (per-host concurrency, default 5), its turn under `--rate`, the global cap, the URL limit, the watchdog and the network pause's gate and probes, and later retries. Nothing else calls the Fetcher; a guard in `tests/test_code_style.py` names any request made elsewhere.
- **Fetcher:** aiohttp behind an interface, so httpx2, niquests or Playwright (v1.1) can replace it. It makes one hop; `022` follows redirects hop by hop and records every hop. HTTP version is measured once per host with a TLS ALPN check.
- **Page executor:** in process, or `026`'s process pool, so that parsing never blocks the event loop.
  - Extractors turn a response into Page data, Links and Resources.
  - lxml is loaded only when an XPath Custom Extraction exists (v0.3).
- **Rules:** run per Page as data arrives, then in a pass after the crawl for checks across Pages (duplicates; site-wide Rules from v0.2).
- **Writer:** the only writer, flushing in batches. A crash loses at most the unflushed batch.
- **Process model:**
  - `crawl` runs in the foreground by default.
  - `--detach` starts a separate background process (CREATE_NO_WINDOW on Windows, so the parse workers open no console windows; `start_new_session` on POSIX).
  - `status`, `stop` and `resume` talk to it through control rows in the store, so no OS signals are needed.
- **As built by `020-add-crawl-core`:** the Crawl Service builds one `CrawlContext` (`spider.crawl.engine.context`) for a Crawl: its settings, the Scope, the clock, the warning log, the writer, the Fetcher, the page executor, the hooks and the stop flag. The engine takes it: `spider.crawl.engine.dispatch` runs the depths and builds the run's Requester and robots.txt loader; `spider.crawl.engine.units` decides each URL and requests it through the Requester; `spider.crawl.engine.outcomes` follows each unit to its outcome; `spider.crawl.engine.crawl_warnings` gives the warnings.
  - **The Requester** (`spider.crawl.fetch.requester`): `request_url(url)` takes the host's slot, then its turn under `--rate`, then the global cap, then returns `NotStarted` once the Crawl is stopping or at `--max-urls`, or else counts the request toward `--max-urls` and sends it; `request_robots_txt(url)` takes the same slots and is never counted. The engine and the robots.txt loader (`spider.crawl.robots.loader`) call it and hold no Fetcher.
  - **The Fetcher Protocol** (`spider.crawl.fetch.fetcher`): `async def fetch(request: Request) -> FetchResult | FetchFailure`. It makes one hop and never follows a redirect. A `FetchResult` holds the status, the reason phrase as received, the raw headers in order and letter case, the body, `fetched_at` and `response_time_ms`. A request without an HTTP response is returned as a `FetchFailure` (its `fetch_error` code, a message, `fetched_at`), never raised; only cancellation passes through. `AiohttpFetcher` is the implementation; `022` replaces it behind the same Protocol.
  - **Hooks** (`spider.crawl.engine.hooks`): a frozen `Hooks` of extractors, per-response handlers and post-crawl passes. `default_hooks()` in `spider.services.hooks`, the composition root, lists the built-in ones explicitly, with no plugin discovery, so the crawl core never imports its plugins; the Crawl Service takes the `Hooks` to use, so a test passes its own without leaking into another test.
    - **Extractors** (`spider.crawl.pages.preparation.Extractor`): a name and a pure, module-level function of the parsed tree and a frozen `PageInput` (the URL, status, headers, the decoded length, the Links, those of the `Link` and `Refresh` headers first, the robots directives, the settings snapshot) and its own config to a frozen `msgspec.Struct`, the type its return annotation declares: one that returns another is an extractor error, and a handler reads the output with that extractor's `output(result.outputs)`, typed. The config is a `msgspec.Struct` with frozen fields (a shallow check) or `None`, resolved where the hooks are built and carried with its extractor in the settings snapshot, so `PageSettings` has no field of any one extractor; extractors are built only with `extractor(name, extract, config)`, so mypy rejects a config of another type than its function's wherever the extractor is registered, inside `Hooks(...)` too. Module-level, so that `026`'s workers import it by name. Page preparation runs them over the one tree it parses; one that raises costs only its output.
    - **Handlers** (`Handler[R]`): a name, a pure function of a `UrlResult` (the URL's row values; for a fetched URL its `response`, a `UrlResponse` with the status, the reason phrase, the Content-Type, the headers, `fetched_at`, the response time and the robots directives, and its extractor outputs by name; for an in-Scope 2xx response the `links` the engine read, each with its `declared_in` and `requests_target`; for an errored URL its `failure`, a `UrlFailure` with the fetch error, its message and `fetched_at`) to rows of one type `R`, and `write`, the store function that writes them. One handler, one row type, one table: a handler that fills two tables is two handlers. Handlers are built only with `handler(name, handle, write)`, so mypy rejects a writer of another row type wherever the handler is registered, inside `Hooks(...)` too; a guard in `tests/test_code_style.py` names a `Handler(...)` built elsewhere. A handler's rows for a URL are written once per recorded outcome, with its final state, `fetched`, `error` or `skipped`, at dispatch, and a handler never writes to the store itself; a URL that a network pause re-queues is recorded again (see the crawling spec's Per-response hook). A URL that a shorter path queues again reaches its handlers again, and the rows of the earlier call are discarded, so a handler must have no side effects. A URL that only unfollowed Links reach (`nofollow`, `link_type_not_followed`) is recorded `skipped` when it is discovered, and no handler sees it, since a later followed Link may still queue it; nor does one skipped beyond `--max-depth`, which a shorter path may still re-queue.
    - **Store rows:** frozen dataclasses with slots, declared in a module of `spider.store` that loads no sqlalchemy. The store module that owns their table defines the function that writes a handler's rows for a URL, given as one sequence, with one `executemany` of a statement built at import; the handler names it; the URL's own writer unit writes each handler's rows with that handler's writer and its final state, so they commit together.
    - **The page executor** (`spider.crawl.pages.preparation.PageExecutor`): `start(settings)` once, with the settings snapshot of the final Scope, then `prepare(url, response)` per parsed response, and `close()` when the Crawl ends, also when it fails. `backlog` is how many Pages it may hold beyond the requests in flight; the engine bounds the URL tasks in flight by the global request cap plus it. `default_page_executor()` in `spider.services.hooks` selects the in-process executor; `026`'s process pool takes its place.
    - **Post-crawl passes** (`Pass`): a name and a function of one frozen `PassContext` (the writer and the clock; a later dependency is a new field) that submits its own units, which store functions build. A pass that needs more than the store lives above it and only orders the store's units, as `040`'s, which needs the Rule catalogue. They run one after another, in the order `Hooks` declares them, so a pass may read what an earlier one wrote, after the last URL is recorded and before `completed` or `stopped` is written, so `040` can read either as "the passes have run".
  - **The stop flag** (`spider.crawl.engine.stop`): a `StopSignal`, set once with its `stop_reason`, stops the dispatch of new requests, and a `StopGrace` gives the requests in flight one grace of clock time from the stop. `spider.services.interrupts` sets it on an interrupt while a foreground Crawl runs: Ctrl+C or Ctrl+Break on Windows, SIGINT, SIGTERM or SIGHUP on POSIX, and a second interrupt ends the process at once. `spider.services.crawl_failures` builds the error that a failed or interrupted Crawl ends with.
  - **The network pause** (`spider.crawl.engine.pause`): a `NetworkPause` counts Internal requests in a row that got no HTTP response, from each URL's outcome. At its count, the Requester holds new requests at the pause's gate and makes the probes. The pause ends as an outage, whose URLs are requested again, or as a dead section, or it fails the Crawl when no probe answers within `--network-wait`.
  - **Progress** (`spider.crawl.engine.progress`): `UrlCounters` keeps the `urls` counts from the committed units, and `report_progress` writes a `progress` event every 10 seconds of clock time.
  - **Continuing a Crawl** (`continue_crawl` in `spider.services.crawling`): it continues a `stopped` or `failed` Crawl from its crawl file alone, with the settings, Scope and Seed recorded there, and queues again its `error` URLs and those skipped as `robots_unreachable`. Then it runs as a start does, to the same end and the same passes. `060`'s `resume` calls it.
  - **How `030` and `040` plug in:** `030` adds its Page extractor, with its config, its handlers, one per table, and its inlink pass to `default_hooks()` in `spider.services.hooks`, importing `Handler`, `Pass`, `PassContext` and `UrlResult` from `spider.crawl.engine.hooks` and `is_html_type` from `spider.crawl.pages.preparation`, with its row types and the writers its handlers name in `spider.store.pages` and `spider.store.links`; `040` adds its pass, which materialises the Issues of its Rules, in `spider.store.issues`. Neither touches the engine.
- **Output streams:** stdout carries the Command's single JSON result (or NDJSON rows for data streams). stderr carries JSON lines: diagnostics and progress events. Settings come only from flags and `spider.toml`, never from environment variables.

## Crawl store

- **Files:** one SQLite file per Crawl, `<data folder>/crawls/<crawl-id>.sqlite` ([crawl-store.md](crawl-store.md)).
  - WAL mode lets agents query while the writer works. On a UNC path it falls back to rollback-journal mode and warns with `store_wal_unavailable`; the setting `store.journal_mode` covers other network folders.
  - The schema is a public, versioned contract ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)), documented in [schema.md](schema.md).
- **The public API,** which every change that stores or reads Crawl data builds on:
  - **Creating a Crawl:** `spider.services.crawls.create_crawl(NewCrawl, clock, reporter)` draws the crawl id, creates the file exclusively, chooses the journal mode, redacts secrets, and writes the `crawl` row and the Seeds in one transaction.
  - **The writer:** `spider.store.writer.CrawlWriter` runs units of work on its own thread inside one open transaction ([crawl-store.md](crawl-store.md#writing-a-crawl)). It commits every 500 units, every second, after a failing unit, on `flush()` and on `close()`, refuses an unwritable file before anything is crawled, and is the only writer after creation.
    - **The optimistic batch:** units run with no savepoint each. When one fails, the writer rolls back, runs the units before it again and commits them, and the failing unit gets its own error. A unit may run twice, so it has no effect outside its connection.
    - **Waiting or submitting:** `run()` and `run_async()` return a unit's result once it has run. `submit()` and `submit_async()` return a Future that resolves at the commit that holds the unit, with its result or the error of a failed commit. At most 2,000 submitted units are unresolved at once, and a submit waits for room.
    - **Its connection settings:** temporary tables in memory, a 64 MiB page cache and, in WAL mode, 256 MiB of memory-mapped I/O. Creating a file and reading it keep SQLite's defaults.
  - **`--crawl` resolution:** `spider.store.selection.resolve_crawl` turns `latest`, an id or a path into a crawl file, and `spider.store.reading.reading` opens one read-only for a single operation, refusing a file from a newer tool.
  - **The schema service:** `spider.services.schema.describe_schema` describes the public tables for `spider schema` and the MCP server: columns with their references, and secondary indexes. `spider.services.schema_doc.parse_tables` reads the table sections of `docs/schema.md` back.
  - **Redaction:** `spider.store.redaction.redact`, with the secret names that the adapter creating a Crawl collects through `spider.cli.options.secret_names`, from the secret settings and options already declared.
  - After the exclusive create of a new file, `spider.store.connections` is the only code that opens a crawl file: one engine per operation, disposed after it, so no handle outlives the operation.
- **Schema definition:** SQLAlchemy 2 Core tables in `spider.store.schema` are the single definition ([ADR-0003](adr/0003-sqlalchemy-core-not-orm.md)). They drive batched inserts, safe `--where` → SQL translation (only known columns), and the SQL reference (`spider schema`, the Skill).
  - **The conventions** are [ADR-0005](adr/0005-crawl-file-schema-conventions.md): names, keys and references, units, flags, enumerations, errors, indexes, and derived and later columns.
  - **The one way to declare a public table** is `public_table(name, *columns, comment=..., change=<n>)` in `spider.store.schema`. It makes the table `STRICT` and adds a CHECK for every enumeration and flag column, so the file refuses a value of another type or outside its list, whatever writes it. No CHECK is written by hand.
  - Every table, column and index has a description, because the descriptions feed that reference.
- **Prebuilt statements:** a unit that runs once per URL or per Page executes statements built once at import, as `execute(stmt, params)`. It never builds `.values(<literals>)` per unit, and never uses `insert().values(list)`.
  - In the store benchmark, a statement built per unit regenerated its cache key and coerced every value, so prebuilt statements were about twice as fast. A multi-values insert compiled per call was 60 times slower than `executemany`.
  - Units that run a bounded number of times per Crawl, such as the write check and setting the state, may build their statements where they run.
  - No guard test enforces the rule. A check over the source cannot tell a statement built once from one built per call: expanding bind parameters and column lists chosen at import look the same as statements built per call. The review of every task group that adds units checks it instead, and a guard is reconsidered if a review finds the rule broken twice.
- **The three-way schema check,** so the documentation, the code and the files cannot drift apart:
  - `docs/schema.md` is compared with `spider schema --limit 1000`
  - a new crawl file is compared with the declared tables through `PRAGMA table_list`, `table_info`, `foreign_key_list`, `index_list` and `index_xinfo`, and the CHECK names and partial-index conditions in `sqlite_master`
  - the table conventions are checked over every declared table
- **Tables:** each change adds its own tables and columns to the declaration and to `docs/schema.md` in the same slice ([CONTRIBUTING.md](../CONTRIBUTING.md#changing-the-crawl-store-schema)). There are no migrations before v0.1, and schema version 1 is the first public contract; Alembic arrives with the first schema change after it.
- **The startup path:** `sqlalchemy` is imported only inside the bodies of the Commands and services that use the store, so `spider --help` and `spider commands` never load it.
- **Read-only access:** `spider sql` opens the file with a read-only URI plus the SQLite authorizer.
- **Missing values:** a value that is not measured yet is `NULL`, never 0 ("not measured" differs from "zero"). A derived column is `NULL` until its post-crawl pass, and a later column until its release.

## Page data

| Group | Columns |
|---|---|
| Identity and response | Address, URL-encoded address, Content Type, Status Code, Status, Indexability, Indexability Status, Response Time, Last Modified, Redirect URL, Redirect Type, Cookies (Set-Cookie), HTTP Version, Crawl Timestamp |
| Titles and headings | Title 1/2 (+ length, pixel width), Meta Description 1/2 (+ length, pixel width), Meta Keywords, H1-1/2 (+ length), H2-1/2 (+ length) |
| Directives | Meta Robots, X-Robots-Tag, Meta Refresh, Canonical Link Element, rel next/prev (HTML and HTTP header), amphtml, Mobile Alternate |
| Size | Size, Transferred, Content-Encoding |
| Content | Word Count, Sentence Count, Average Words per Sentence, Flesch Reading Ease / Readability, Text Ratio, Language, Hash, Closest Near-Duplicate†, Near-Duplicate count† |
| Links | Crawl Depth, Folder Depth, Link Score†, Inlinks, Unique Inlinks, Unique JS Inlinks†, % of Total, Outlinks, Unique Outlinks, Unique JS Outlinks†, External Outlinks, Unique External Outlinks |
| Structured data | JSON-LD / Microdata item counts and types, validation errors† / warnings† |

† These columns are null until the release that measures them (see [ROADMAP.md](../ROADMAP.md)).

## Report pipeline

```
Crawl Store ──► ReportModel ──┬──► HTML renderer ──► report.html (+ CSV files for full lists)
 (same model as `summary`)    │        ▲
                              └──► Section Briefs (JSON per Report Section)
                                       │  one subagent per Report Section writes notes/<section>.md,
                                       │  the main agent writes notes/summary.md
                                       └──── Report Notes (Markdown, raw HTML disabled)
```

- **The file:** a single self-contained file, with SVG charts and no CDN, so it works offline and can be emailed.
- **Security:** crawled text is untrusted and is always escaped.

## Agent integration

- **Skill:** generated from the CLI's command metadata, stamped with the version, and installed with `spider skill install` into `~/.claude/skills` (Claude Code) and `~/.agents/skills` (Codex and most other agents). The repo keeps a generated copy in the standard layout for plugin marketplaces and `npx skills add`.
- **MCP server:** `spider mcp` (MCP Python SDK 2.x, stdio). It ships as a `.mcpb` for Claude Desktop, and its tools return the same JSON as the CLI.
- **Plugin marketplace:** `.claude-plugin/marketplace.json` in the repo, read by both Claude Code and Codex.
- **Self-description:** `spider commands --format json`, which is the source the Skill is generated from.

## Cross-platform rules

- CI runs on Windows, macOS and Linux × Python 3.12–3.14. `requires-python` is `>=3.12,<3.15` until the dependencies ship Python 3.15 builds.
- Output is written as UTF-8 bytes (Windows pipes default to the ANSI code page until Python 3.15), and `-o <file>` avoids shell encoding problems altogether.
- Use `pathlib` everywhere and `asyncio.run(..., loop_factory=...)`, not event-loop policies.
- SSL certificates come from the OS trust store via truststore, falling back to certifi.
- Detached processes use OS-specific creation flags, and control never relies on signals.

## Package layout (target)

```
src/spider/
  cli/          Typer app, one module per command group
  mcp/          MCP server
  naming.py     the product name and the names made from it
  services/     workspace (init), query, crawl, report
  workspace/    Workspace discovery, settings (spider.toml)
  output/       JSON/table/CSV serialisation, the Reporter, paging, diagnostic codes, exit codes
  store/        schema (Core tables), writer, migrations/, read-only access
  crawl/        engine, requester, fetcher, robots and its loader, scope, pages, hooks
  extract/      Page data extractors, links, content, readability, pixel widths
  rules/        Rule registry, rule modules, thresholds, Health Score
  query/        --where language, paging, Segments
  report/       ReportModel, Section Briefs, templates/, charts
  skill/        Skill generator and templates
tests/
  fixture_site/ local test site used by every change
```

## Stack

| Concern | Choice |
|---|---|
| Language | Python ≥3.12, <3.15 |
| HTTP | aiohttp (behind a Fetcher interface) |
| HTML parsing | selectolax (Lexbor); lxml only for XPath |
| robots.txt | Protego |
| Store | SQLite + SQLAlchemy 2 Core + Alembic |
| CLI / settings | Typer, pydantic-settings |
| JSON | msgspec / orjson |
| MCP | MCP Python SDK 2.x |
| TLS trust | truststore (certifi fallback) |
| Tests | pytest + local fixture site |
| Packaging | uv (`uv tool install`), PyPI |
