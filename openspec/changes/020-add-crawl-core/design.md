## Context

- **What this change builds on:**
  - `000-scaffold-project`: `spider.aio.loop_factory`, `spider.clock.Clock` with `SystemClock` and the test `FakeClock`, the network guard, and the fixture site with its request log and its `delay` and `hang` options.
  - The archived `010-add-workspace-and-cli-contract` (openspec/specs/workspace and cli-contract, and its design):
    - a Command is an adapter plus a service with typed inputs and a `Reporter` (`warn`, `event`); `Collected` keeps the calls in memory (010 D9)
    - partial results: a Command returns `Outcome(result, SpiderError)`, the runner prints the result, then the one error (010 D5)
    - the code registry in `spider.output.codes`, with `ExitCode.USAGE` (2), `BUSY` (5), `IO` (7), `NETWORK` (8), `INTERRUPTED` (130) and the declared `interrupted` and `invalid_value` (010 D5)
    - the settings registry: tables registered in `build_app` as `"module:Class"`, one owner per table, `None` defaults, `secret` on the settings field, flag > `spider.toml` > default (010 D2)
    - `@command_meta(name=CONST, output="document", events=True)` and `OptionMeta(setting=...)` (010 D7), the startup allowlist test (010 D10), and `spider.naming` (010 D11)
  - `015-add-crawl-store`, groups 1–9 as built on its branch:
    - `spider.services.crawls.create_crawl(NewCrawl, clock, reporter)` returns a `CrawlFile(id, path)`; the `crawl` row and `seeds` are written in the file's first transaction. It chooses the journal mode from `NewCrawl.journal_setting` (`JournalSetting`: `auto`, `wal` or `delete`, default `auto`) and reports `store_wal_unavailable` through the Reporter
    - the `[store]` table, `spider.store.settings:StoreSettings` with `journal_mode`, registered in `build_app`
    - redaction: `NewCrawl.secret_names` is a required `SecretNames(flags, settings)` (in `spider.store.records`), which an adapter gets from `spider.cli.options.secret_names(command, tables)`; `create_crawl` redacts the command line and config with it before anything is written (015 D7)
    - `CrawlWriter(path, clock, on_commit=None)`: `await run_async(unit)`, a unit is `Callable[[Connection], T]` run in its own savepoint, commits every 500 units or 1 s, `close()` commits and checkpoints. Opening and `close()` block, so they run through `asyncio.to_thread`. A writer whose thread ends raises `CrawlWriterClosedError` to every later caller, and a busy file is `crawl_busy` (exit 5)
    - `set_state(connection, state, at)` in `spider.store.crawls`, which sets `completed_at` only for `completed`
    - the shared column types `Timestamp`, `Json` and `Flag`, `info={"change": <n>}` and comments on every table and column, and the contract test against `docs/schema.md`
    - `CrawlState` and `CrawlMode` as `Literal`s in `spider.store.records`, which loads no sqlalchemy
  - `015`'s group 10 (wrap-up docs) adds no interface this change uses.
- **`018-add-schema-conventions` and ADR-0005,** before this change in the build order (015 → 017 → 018 → 020):
  - every public table is declared through `018`'s declaration helper, which makes it `STRICT` and adds the CHECKs of its listed values and flags
  - `spider schema` reads `references` from declared foreign keys, and lists each index with the query it serves
  - the contract test also compares indexes, STRICT and `WITHOUT ROWID`
  - the schema blueprint of 2026-10-11 and its rulings decide this change's tables (D18)
- **ADR-0001:** an own asyncio engine on aiohttp, whose frontier lives in the crawl store; the Fetcher sits behind an interface.
- **ROADMAP decisions of 2026-10-05:** no default `--max-urls`, the robustness rule, 060-min in v0.1, and four design points from the architecture review (D12–D15).
- **The split of the crawler:** this change is the core. `022` adds the fetch policy, `060`-min background Crawls and `resume`, `026` the benchmark (and a pool only if it is needed), and `024` the other Crawl Modes in v0.2. Each plugs in without reworking the core.
- **The thin slice** (ROADMAP, Build order: 015 → 020 → 030-min → 040-min → 050 issues) needs from this change: normalisation, the host Scope, hyperlink discovery, a foreground Crawl that writes `urls` through the writer, `is_internal`, `fetch_error`, the result and exit codes, and the hooks that `030` and `040` plug into. tasks.md marks those groups `slice`; the rest widens.
- **Platforms:** Windows, macOS and Linux × Python 3.12–3.14, with `asyncio.Runner(loop_factory=loop_factory)`.

## Goals / Non-Goals

**Goals:**
- A foreground Spider-mode Crawl that behaves like Screaming Frog's spider for Scope, Link following and robots.txt, with every decision visible in `urls.fetch_state` and `urls.skip_reason`.
- Built for a 500k-URL Crawl: memory that does not grow with the number of URLs (D1), no default limit, and no single URL that can stop the Crawl (D16).
- A frontier that is consistent at every commit, and a continue operation that `060` exposes as `resume`.
- Stable extension points for `022`–`060`: the Fetcher interface, the hooks, the extractor registry, the robots directives parser, the transition check and the Crawl context.
- A functional core: pure functions over frozen dataclasses for every decision (normalisation, Scope, robots, directives, Link extraction, transitions), and an imperative shell (engine, scheduler, service) that takes one context object.

**Non-Goals:**
- Fetch policy, other Crawl Modes and the process pool (`022`, `024`, `026`).
- Background processes, the writer claim, control rows and the `interrupted` state (`060`).
- Storing Links or Page columns (`030`), and evaluating Rules (`040`).

## Decisions

### D1. The `urls` table is the frontier
Each distinct normalised URL has one row, and its `fetch_state` (`queued` → `fetched` | `error` | `skipped`) is the queue.
- **No in-flight state:** there is no separate frontier table and no persisted "in flight" state. A URL leaves `queued` only in the writer unit that stores its response and the URLs discovered from it. After a crash, anything in flight is still `queued`.
- **No in-memory URL map:** discovered URLs are inserted with `INSERT … ON CONFLICT (url) DO NOTHING` inside the URL's unit, and the unit reads back the ids it needs. The unique index `urls_url` is the only dedup, so memory does not grow with the site. What the process keeps in memory is bounded by the site's shape, not its size: the URLs in flight (at most the global cap of D7), one robots.txt verdict cache and one politeness gate per origin, the 60-second rate window, and the warnings.
- **Dispatch order:** the scheduler takes queued URLs of the open Crawl Depth in batches, through a unit, ordered by `urls.id`. SQLite gives an `INTEGER PRIMARY KEY` the next larger value and URLs are never deleted, so `id` grows in the order URLs are first recorded. It is the explicit insertion sequence that 015's conventions ask for, so no separate `seq` column is added and no timestamp is ever a tie-break.
- **Continuing:** the continue operation first re-queues URLs that ended with no response (`error`) or were blocked by an unreachable robots.txt. Those outcomes are usually transient, and this is what makes a `failed` Crawl resumable. It also inserts the `urls` row of any Seed that has none, because a process can die between creating the Crawl and recording its first unit.
- *Alternative:* a separate `frontier` table. It duplicates URL identity and needs two writes per URL. Rejected.
- *Alternative:* an in-memory URL-to-id map, as the draft had (about 100 bytes per URL, 50 MB at 500k and growing). It contradicts the flat-memory promise once `--max-urls` has no default. Rejected; `026`'s benchmark measures the index lookups instead.

### D2. One writer unit per completed URL
The unit of `015`'s `CrawlWriter` is one completed URL, submitted with `await writer.run_async(unit)`. It holds:
- the `urls` update of that URL
- the inserts for the URLs discovered from it
- the rows its per-response handlers returned (D9)

The writer batches units into commits (500 units or 1 second, 015 D4), so a killed process loses at most about a second of work, and those URLs are still `queued`. The engine opens the writer, and closes it at the end, through `asyncio.to_thread`. Progress counts come from the writer's `on_commit` callback plus a counting unit, never from a counter stored on `crawl` (015's conventions).

### D3. Followed URLs are dispatched depth by depth
No followed URL (an Internal URL in the Scope) at depth d+1 starts until every followed URL at depth ≤ d has been processed. Checks, meaning External URLs, URLs outside the Scope and Resources, never block that barrier. Crawl Depth is then exact however responses interleave.
- **Redirects:** `022`'s redirect targets inherit their source's depth and join the depth that is still open, so the barrier stays exact with zero-weight edges.
- *Alternative:* free order with depth lowering. Descendants of a URL whose depth was lowered late keep a wrong depth. Rejected.
- **Cost:** a stall at each boundary until the slowest internal Page of that depth is processed, bounded by the request timeout and the watchdog.

### D4. The Scope model
- **`ScopeRules`** is a frozen dataclass built once from the Seed and the settings, with a pure method from a `NormalizedUrl` to `is_internal`, `in_scope` and an optional skip reason. The host rule (`host`, `subdomains` or `subfolder`) matches on the host only, any scheme and any port. `--include`/`--exclude` come after it, and exclude wins.
- **Seed hosts and the www rule:** the Seed's host, plus `www.<host>` when the Seed's host is a registrable domain. One direction only: a `www.` Seed never admits the apex, because the reverse would quietly widen a Crawl to a host the user did not name. An IP address or a host without a registrable domain gets no `www.` host. A table-driven test of about 20 Seed/URL cases pins the rule: apex, `www.`, other subdomains, ports, IDN hosts, public suffixes such as `co.uk`, IP addresses, single-label hosts and upper case.
- **`seed_base_mismatch`:** decided from the Seed's parsed Links (its `canonical`, and the hosts of its `hyperlink` Links), once, after the Seed is recorded. It warns; it never changes the Scope.
- **Registrable domains** come from `publicsuffixlist`, which ships the list and never downloads it.
  - *Alternative:* `tldextract`. It downloads on first use unless configured otherwise, which is surprising network traffic for a tool without telemetry. Rejected.
- **Flag shape:** one enum plus the `--subdomains` shorthand that ROADMAP names.
  - *Alternative:* orthogonal flags. They double the combinations to test for the rare "subfolder on every subdomain" case, which `--scope subdomains --include` already covers. Rejected.
- **`--exclude` means never requested,** because it exists to keep a Crawl away from logout links, cart actions and calendars. **`--include` makes a Section Crawl**, whose outside URLs are checked but not followed.

### D5. Request versus parse, and the Link type table
Two independent decisions:
- **Request** depends on the Link type table, nofollow, the Scope, robots.txt and the limits.
- **Parse** depends only on the URL being in the Scope with a 2xx HTML response. A Resource Link that returns in-Scope HTML is therefore parsed, and is not a Resource under the glossary.

**The link extractor** is ours. It parses the HTML once with selectolax's lexbor backend, `selectolax.lexbor.LexborHTMLParser`; selectolax 1.0 removed the old `selectolax.parser` backend. It produces:
- `DiscoveredLink` values (frozen msgspec structs): type, normalised target or null, raw value, element, attribute, rel tokens, nofollow, where it was declared (`declared_in`: `html` or `http_header`, the name of `030`'s column; `origin` means scheme, host and port only, ADR-0005 rule 9), and position in the HTML
- the page-level robots directives

The engine's discovery step consumes them. **`030` enriches** each `DiscoveredLink` with analysis attributes through its own extractor over the same parsed tree, and stores them. It never redefines discovery.

**The Link types** (the rulings of 2026-10-11 on Screaming Frog's ~28 types):
- **Added in v0.1:**
  - `http_refresh`: the `Refresh` header, read by the same parser as a meta refresh
  - `misc`: other `<link rel>` values, recorded but not requested, as `amphtml` is
  - `video` and `audio`, split from `media`. `<embed>` and `<object>` stay `media`, which `030` may revisit before v0.1.
- **Listed from v0.1 and filled later:** `xml_sitemap` and `sitemap_hreflang` (`024`, v0.2), and `javascript_redirect` (v1.1).
- **Not Link types:**
  - HTTP redirects: they are `urls.redirect_url_id` (`022`)
  - HSTS
  - SWF, which is obsolete
  - PDF, which is a content type
  - Font, which needs CSS parsing
- **One list:** the types are one `LinkType` `Literal` in `spider.store.records`. `discovered_via` lists them, and `030`'s `links.type` takes the same list, so no change adds a Link type of its own.
- **One value for sitemaps:** a URL listed in a sitemap is `discovered_via` = `xml_sitemap`. `024` uses that Link type instead of a separate `sitemap` value (ruling of 2026-10-11).

**Decoding:** HTML is decoded in this order, with replacement characters for invalid bytes:
1. a byte order mark
2. the `charset` parameter of `Content-Type`
3. a `<meta charset>` in the first 1024 bytes
4. otherwise UTF-8, falling back to windows-1252

`030` documents the same order for text, and both go through one shared function.

### D6. robots.txt and the robots directives
- **Parsing:** Protego parses robots.txt, and the verdicts are cached per origin for the run. Only the first 512,000 bytes are parsed, decoded as UTF-8 with replacement.
- **Status mapping:** the RFC 9309 mapping (2xx `ok`, 4xx except 429 `missing`, 5xx/429/no response `unreachable`, more than 5 redirects `missing`) is a pure function.
- **The robots.txt request** follows its own redirects internally, up to 5 hops. It goes through the same politeness gate and counts for `--rate`, but not for `--max-urls`.
- **Crawl-delay** is recorded, not applied, which matches Googlebot and Screaming Frog.
- **The robots directives parser** is a pure function from meta `content` values, `X-Robots-Tag` header values and the robots token to the directive values, named as `030`'s columns (`meta_robots_noindex`, `x_robots_tag_nofollow`, …). `030` imports it, so the two changes can never disagree about noindex or nofollow.

### D7. Politeness
- **Per-host limits:** a semaphore per host (`--concurrency`) and a per-host "next allowed start" time (`--rate`).
- **Global cap:** 4 × concurrency, clamped to 20–100, bounds sockets when many External hosts are checked.
- **Clock:** all waiting goes through the context's `Clock` (`monotonic()`, `sleep()`), including the watchdog and the stop grace period (D16), so `FakeClock` drives every timing scenario.
- **Blocking detection:** a counter of consecutive 403/429 responses per Internal host.
- `022` adds retry backoff and `Retry-After` pauses on the same per-host gate.

### D8. The minimal Fetcher
- **The interface:** a `Fetcher` Protocol, `async def fetch(self, request: Request) -> FetchResult`, over frozen dataclasses. It makes exactly one hop and never follows redirects. `022` replaces the implementation without changing the Protocol.
- **The aiohttp implementation in this change:**
  - raw response headers in order and letter case
  - a fixed 20-second total timeout, which `022` makes configurable
  - aiohttp's default TLS context, which `022` replaces with truststore
  - a DNS resolver hook (an aiohttp resolver), which tests use to map host names to fixture instances
- **Errors** are returned in the `FetchResult`, never raised: name resolution → `dns_error`, `ConnectionRefusedError` → `connection_refused`, protocol errors → `invalid_response`, and every other exception of the request, a reset included → `connection_error`, with the exception type in `fetch_error_message`. Only cancellation passes through.

### D9. Hooks and the extractor registry
- **`Hooks`** is a frozen dataclass of tuples, part of the Crawl context (D15): extractors, per-response handlers and post-crawl passes. `default_hooks()` in `spider.crawl.hooks` lists the built-in ones explicitly, with no plugin discovery; `030` and `040` add theirs to that list. A test passes `default_hooks()` plus its own entries to the Crawl Service, so nothing registered for one test leaks into another.
- **Extractors** are pure: a name and a function from a parsed tree to a msgspec struct. They run in the crawl process in this change. If `026` builds its pool, it moves the same functions into worker processes; msgspec structs cross the process boundary as they are.
- **Per-response handlers** are pure too: a name and a function from a `UrlResult` (the URL's row values, and for a `fetched` URL its status, headers and extractor outputs) to a sequence of store rows (D14). They run for every URL that reaches a final state, including `error` and `skipped`, so `030` can record cookies on any status, and `040` can evaluate Rules on single URLs.
- **Post-crawl passes** run when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written. A pass is a store function (D14) that submits its own units, so a pass over 500k Pages can write in batches. `030` computes inlink counts there, and `040` runs the reproducing SQL query of each Rule that spans Pages. Passes run again after every continued run, so they must be safe to re-run, and they never run for a `failed` Crawl or a killed process.
- *Alternative:* module-level registries, as the draft had. Tests that register into them leak into each other. Rejected.
- *Alternative:* "sinks" that turn extractor structs into rows. They are handlers by another name. Merged into handlers.

### D10. Events, result, exit codes and interrupts
- **Events and diagnostics** go through the context's `Reporter`. The Crawl Service wraps it in a warning log that writes each warning once per code and host, keeps it for the result and `crawl.warnings`, and adds `details.count` and `details.first_url` to counted warnings (D16). `progress` is fixed at every 10 seconds.
- **The result** is a frozen dataclass with `to_json()`, built at the end from counting queries over `urls`, never from in-memory counters. The adapter returns it, or `Outcome(result, SpiderError)` for a failed outcome, so `010`'s runner prints it before the one error:
  - `interrupted` (declared by `010`) → exit 130
  - `seed_unreachable` and `site_unreachable` → exit 8
  - `crawl_write_failed` → exit 7, or `015`'s `crawl_busy` → exit 5, as the writer raised it
- **Interrupts:**
  - The Crawl runs under `asyncio.Runner(loop_factory=loop_factory)`. `signal.signal` handles SIGINT (plus SIGBREAK on Windows, and SIGTERM/SIGHUP on POSIX) and sets the stop flag through `loop.call_soon_threadsafe`, because Windows loops have no `add_signal_handler`. So no `KeyboardInterrupt` reaches `010`'s runner during a Crawl.
  - The stop flag is a `StopSignal` in the context: it is set once, with the `stop_reason` the Crawl ends with. `060`'s control rows set the same object.
  - A second interrupt calls `os._exit(130)`. The last committed unit keeps the store consistent (D1).

### D11. Settings and the recorded config
- **The `[crawl]` table** is owned by this change: a pydantic model `CrawlSettings` in `spider.crawl.settings`, registered in `build_app` as `("crawl", "spider.crawl.settings:CrawlSettings")`. It follows `010`'s table rules; `max_urls`, `max_depth` and `rate` default to `None` (written `# max_urls =` in the template), which means "no limit". `022` and `030` add their keys to this model; they never register a second table.
- **Options** declare `OptionMeta(setting="crawl.<key>")`, so `spider commands` lists each option's setting and default, and the scenario "The recorded config holds every registered crawl setting" stays generic. `--subdomains` has no setting: the adapter resolves it into `scope` before loading settings.
- **The recorded config** is the resolved value of every registered table, `[crawl]` and `015`'s `[store]` included, as `NewCrawl.config`. The Crawl Service loads settings once and builds both the `NewCrawl` and the context from them.
- **The journal mode (`015` group 8, built):** the Crawl Service sets `NewCrawl.journal_setting` from the resolved `[store] journal_mode`, in the slice. `create_crawl` reports `store_wal_unavailable` through the Crawl Service's warning log (D10), so it reaches the result and `crawl.warnings` like any other warning.
- **Redaction (`015` group 9, built):** `NewCrawl.secret_names` has no default, so the slice passes it from the start. The `crawl` adapter calls `secret_names(<its Click command>, <the settings tables>)` and hands the result to the Crawl Service, which puts it in the `NewCrawl`; `create_crawl` redacts by itself. `[crawl]` has no secret setting in v0.1, so nothing of it is redacted yet; `022` (v0.2) adds secret ones.
- **Validation and config resolution** are one function the adapter calls before anything is created, so `060`'s detached start and dry run reuse it and cannot disagree with a foreground Crawl.

### D12. Crawl State transitions
- **The table:** `TRANSITIONS` maps each allowed `(from, to)` pair to the `stop_reason` values it allows: `running` → `completed` (none), `running` → `stopped` (`max_urls`, `interrupt`, `requested`), `running` → `failed` (`seed_unreachable`, `site_unreachable`, `write_failed`), and `stopped` | `failed` → `running` (none). `StopReason` is a `Literal` next to `CrawlState` in `spider.store.records`, so `015`'s `values` mechanism documents the column from it.
- **The check:** one pure function, `check_transition(current, target, stop_reason)`, raises `CrawlStateError` for anything else. It is a bug in the caller, so it reaches the agent as `internal_error` (exit 70), never as a quiet wrong state.
- **One writer of the end of a Crawl:** `015`'s `set_state(connection, state, at)` gains the `stop_reason`, reads the current state on the same connection, inside the caller's unit, runs the check, and writes `state`, `stop_reason` and `completed_at` together. Nothing else writes those columns.
- **`060`** adds `running` → `interrupted` and `interrupted` → `running` to the table, and records `interrupted` from another process through the same unit.
- *Alternative:* a state-machine library. One dict and one function are enough, and stay readable in `docs/crawling.md`. Rejected.

### D13. URL types
- **`NormalizedUrl = NewType("NormalizedUrl", str)`** in `spider.crawl.urls`, a leaf module that imports nothing else of `spider`, so the store's row types can use it too. Only the normaliser returns it; the store's reads of `urls.url` cast to it, in one place each. mypy then refuses a raw `str` wherever the frontier, `ScopeRules`, `DiscoveredLink` or the store rows expect a normalised URL.
- **The normaliser never raises:** it returns `NormalizedUrl | InvalidUrl`, where `InvalidUrl` is a frozen dataclass with the reason. The Seed parser maps it to `invalid_url`; the link extractor drops the reference (030 keeps the raw value).
- *Alternative:* a frozen class with parsed parts. It allocates per URL on the hottest path (every Link of every Page), and every SQL boundary would convert it back to text. Rejected; the host and origin are derived with small pure functions where they are needed.
- **Crawl ids stay `str`.** They are created and validated in one place each (`015`'s `new_crawl_id` and `is_crawl_id`), flow through `CrawlFile`, and are never mixed with URLs. A `CrawlId` type is worth it when `060` accepts ids from users; that change decides it.

### D14. Data access stays in the store
- **The rule:** writer units are defined only in `spider.store.*` modules. The engine, the extractors and the Rules build frozen values and call store functions that return units; they never write SQL. ruff's banned-API rule (TID251) bans `sqlalchemy` in `src/`, with per-file-ignores for `src/spider/store/**` and `src/spider/services/schema.py`, which imports it lazily. A lint rule is checked on every commit and costs no new test; `010`'s startup allowlist test stays as it is.
- **This change's store modules:** `spider.store.urls` (the table, recording a Seed, the next batch, recording a completed URL with its discovered URLs and handler rows, re-queueing on continue, and the counts), `spider.store.origins` (an origin's row, recorded in the unit of its first URL, and its robots.txt), and `spider.store.crawls` (`set_state`, the Scope and the warnings).
- **How `030` and `040` add theirs:**
  - **Rows:** a handler returns store rows: frozen dataclasses declared in a module of `spider.store` that loads no sqlalchemy, as `spider.store.records` does today. The store module that owns the table registers the function that writes each row type, and the URL's unit writes the rows it is given through those functions. So `030` adds `spider.store.pages` and `spider.store.links`, and `040` adds `spider.store.issues`.
  - **Passes:** a post-crawl pass is itself a store function, for example `030`'s inlink counts in `spider.store.links` and `040`'s query Rules in `spider.store.issues`.
- *Alternative:* handlers that get the `Connection`. Every later change would then write SQL from extractors and Rules, which this rule exists to prevent. Rejected.

### D15. One context for a Crawl's dependencies
- **`CrawlContext`** is a frozen dataclass: the `CrawlFile`, the resolved `CrawlSettings`, the `ScopeRules`, the `Clock`, the `Reporter` (the warning log of D10), the `CrawlWriter`, the `Fetcher`, the `Hooks` and the `StopSignal`.
- **Built in one place:** an async context manager in the Crawl Service opens the writer and the Fetcher's session, yields the context, and closes both, the writer through `asyncio.to_thread`. The start and continue operations use it; `060` uses it for detached Crawls.
- **Who takes it:** only the imperative shell (the engine, the scheduler, the robots.txt loader and the service). The pure modules (normalisation, Scope, robots, directives, extraction, transitions) take plain values, so they stay table-testable at seam 4.
- **Boundary doubles go in through it:** tests pass a fake Fetcher, `FakeClock` or the DNS resolver hook to the builder. Nothing else of ours is replaced.
- *Alternative:* growing every signature with each dependency. `022` alone would touch most of the engine. Rejected.

### D16. Robustness and backstops
- **Parsers never raise:** the Seed parser, the normaliser, decoding, the link extractor, the directives parser and the robots.txt reader return their result or their own rejection type. Each has a hypothesis property over arbitrary input (bytes, text, malformed HTML) that it never raises, next to its table tests.
- **The engine still contains** an extractor or handler that raises: the extractor's failure becomes `parse_error` = `extractor_error`, with `<name>: <type>` in `parse_error_message`, the handler's drops only its rows, and each is counted in one warning (`parse_failed`, `handler_failed`).
- **The site is lost:** a counter of consecutive Internal requests without a response; any response resets it. At `max(8, 2 × concurrency)` the stop flag is set with `site_unreachable`. It generalises the zero-success breaker of the architecture review: at the start of a Crawl it trips when nothing has answered yet, and later it trips when the network goes away, instead of recording the rest of a 500k-URL site as errors. `failed` stays resumable, and continuing re-queues the `error` URLs (D1).
- **The watchdog:** each request races `clock.sleep(watchdog_seconds)`; the loser is cancelled, and a cancelled request is recorded as `fetch_error` = `watchdog`. One pure function computes `watchdog_seconds` from the settings: `max(120, the Fetcher's total request deadline + 30)`. In this change the deadline is the fixed 20 seconds of D8, so the watchdog is 120 seconds; `022`-min's timeout settings feed the same function, so a watchdog never cuts a slow response that the Fetcher still allows. It is a backstop behind the Fetcher's own timeout, for a hang that the timeout does not cover. A request ended by the watchdog counts as one without a response for the site-lost count.
- **Stop:** grace then cancellation. After the stop flag is set, no request starts; requests in flight get 10 seconds of clock time, then are cancelled without a unit, so their URLs stay `queued`.
- **Writing fails:** the writer raises to the URL's caller and refuses every later unit (`015` D4). The engine sets the stop flag with `write_failed`, and the service tries once to record the end through a fresh writer. A second failure leaves the file `running`, which `060` reports as `interrupted`.
- **Hostile fixtures** added by this change: a connection reset in the body, deeply nested HTML, bytes invalid in their declared charset, and 429 and 503 robots.txt. `022` adds the stalled, trickling, huge and compressed ones with its limits.

### D17. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, each by the slice that first raises it:
- errors, exit 2: `invalid_url`, `option_conflict`, `subfolder_is_root`, `invalid_pattern`, `seed_out_of_scope`
- errors, exit 8: `seed_unreachable`, `site_unreachable`
- error, exit 7: `crawl_write_failed`
- warnings: `seed_blocked_by_robots_txt`, `robots_unreachable`, `possible_blocking`, `max_urls_reached`, `seed_base_mismatch`, `parse_failed`, `handler_failed`

`interrupted` and `invalid_value` come from `010`, and `crawl_busy` from `015`. Hints that name a Command use `spider.naming`.

### D18. The tables under ADR-0005
The schema blueprint of 2026-10-11 and its rulings decide `urls`, `origins` and the new `crawl` columns before they are built. `018`'s helper and contract test enforce what a test can; the review checks the rest of ADR-0005.
- **Declaration:** each table goes through `018`'s declaration helper, so it is `STRICT`, and its enumerations and flags get CHECKs from `info["values"]` and the `Flag` type. No column of this change is derived or filled by a later release, so none carries the `Derived: ` or `Filled from ` prefix.
- **Every value from v0.1:** each enumeration lists the values that `022`, `024` (v0.2) and `026` will write (spec, "The urls table").
  - A CHECK that changes after v0.1 is a schema change with a migration. One that changes inside v0.1 would still make three other changes modify this change's spec.
  - The lists are `Literal`s in `spider.store.records`, so the code, the CHECK and `values` cannot disagree.
- **Names** (ADR-0005 rules 9 and 10):
  - "Blocked by robots.txt" is `blocked_by_robots_txt` in the flag, in `skip_reason` and in the warning `seed_blocked_by_robots_txt`, as in `030`'s Indexability Status and `040`'s Rule id.
  - `parse_error` is a code, with its text in `parse_error_message`, like `fetch_error`.
- **`urls.origin_id`** (ruling Q4) is a declared reference, NOT NULL, so every `urls` row joins `origins`.
  - `origins` therefore holds the origin of every recorded URL, not only of requested ones. The unit that records a URL inserts its origin with `ON CONFLICT (origin) DO NOTHING` and reads back the id, as it does for URLs (D1).
  - An origin none of whose URLs was requested has no robots.txt yet, so `robots_state` and `robots_sitemaps` are nullable.
- **`urls.host` stays:** the politeness limits and the Scope work per host, not per origin (one host serves both http and https), and the scheduler needs the host of every URL it takes.
- **Indexes,** each named `<table>_<columns>` and described by the query it serves:
  - `urls_url` and `origins_origin`, unique, for `ON CONFLICT` and lookups. They are declared as named unique indexes, not as UNIQUE column constraints, because SQLite's automatic indexes for those have no name or description of ours.
  - `urls_crawl_depth_id` on `(crawl_depth, id) WHERE fetch_state = 'queued'`, for the frontier read (D1). Only queued rows are in it, so the unit that records a URL removes its entry.
  - Not indexed, by the rulings:
    - `fetch_state` for counts (Q1): a composite index would add an entry for every URL that is no longer queued. Progress comes from counters (D10), and an agent's `GROUP BY fetch_state` scans, which `080` documents.
    - `fetched_at` (Q2): `060`'s rate comes from its heartbeat's counters.
    - `response_time_ms` (Q3): `050` sorts once.
  - `022` adds `urls_redirect_url_id` on `(redirect_url_id) WHERE redirect_url_id IS NOT NULL`, together with its column.
- **The `crawl` columns:**
  - `scope` is NOT NULL. `create_crawl` writes it with the row, from a `scope` field that this change adds to `015`'s `NewCrawl`.
  - `warnings` is NOT NULL, and `[]` at creation.
  - `stop_reason` takes its values from `StopReason` (D12), the one value set that `060`'s `crawl_runs` shares (ADR-0005 rule 7).
- *Alternative:* `origins` only for requested origins, with a nullable `origin_id`. Every join to `origins` would then need an outer join, and a URL's origin would depend on whether it was requested. Rejected.

## Test seams

Seams from docs/testing.md:
- **Pure-logic modules (4):**
  - URL normalisation: table-driven, plus hypothesis properties (normalising twice changes nothing; any text gives a URL or a rejection).
  - `--strip-params`, the Seed parser, `ScopeRules` with its ~20 Seed/URL cases, and the transition check over every pair of states.
  - The robots.txt status mapping and token groups, the robots directives parser, and decoding.
  - The link extractor (HTML bytes and URL in, Links out).
  - Every parser of D16 gets its never-raises property here.
- **HTTP (local fixture site) (3):** the real engine and the real aiohttp against the plain-HTTP fixture site. aiohttp is never mocked. Multi-host scenarios use two fixture instances behind the **DNS resolver hook**. This change adds to the harness, test-first: the hook, a count of the most simultaneous requests, and a route kind that resets its connection.
- **Seam 3+6:** crawl the fixture site, then read `urls`, `origins`, `crawl` and `seeds` with `015`'s read-only helpers (`query`, `crawl_row`).
- **CLI (1):**
  - Exit codes, stdout and stderr JSON, through `run_cli`.
  - Real subprocess runs on each OS (`run_cli_process`): SIGINT on POSIX, CTRL_BREAK_EVENT to a new process group on Windows, kill/TerminateProcess, and UTF-8 bytes on Windows.
- **Services and store API (2):** the Crawl Service's start and continue operations with a real crawl store in `temp_workspace`. Test handlers, passes and extractors are added to `default_hooks()` and passed in, which is using the extension point, not replacing our code.
- **Store contract (6):** `docs/schema.md` gains every column and index in the same commit as the slice that adds it, so the contract test (`015`'s, which `018` extends to indexes and STRICT) never goes red.

Boundary doubles used, all from the approved list:
- **The fake Fetcher and `FakeClock`:** for rate spacing, Crawl-delay, the progress interval, the watchdog and the stop grace period only.
- **The DNS resolver hook:** for the multi-host scenarios.
- **A full disk:** SQLite's own `max_page_count` limit, set by a test-scoped connection listener, so SQLite reports `SQLITE_FULL` exactly as for a full disk. No file-system fake.

## Risks / Trade-offs

- [Depth barrier stalls on a slow internal Page] → Checks never block the barrier, and the stall is bounded by the request timeout and the watchdog.
- [SQLite write throughput once `030` adds tens of millions of Link rows, plus a unique-index lookup per discovered URL (D1)] → Batched units through `015`'s writer in WAL mode, measured by `026`'s 500k benchmark, which is also the soak test of the robustness rule.
- [In rollback-journal mode (UNC paths, `store.journal_mode = "delete"`), a long read can hold the writer for its 30 s busy timeout and fail the Crawl with `crawl_busy`] → Readers open per operation and are brief; the Crawl is `failed` and resumable; `docs/crawling.md` says to avoid long queries during a Crawl on a network folder.
- [Synchronous parsing cannot be cancelled by the watchdog] → `022` caps body sizes, the hostile fixtures pin deeply nested HTML, and `026`'s pool makes parsing cancellable if its benchmark asks for it.
- [User-supplied regexes applied to URLs controlled by the site (ReDoS)] → `022` caps URL length at 2,000 characters, and docs/crawling.md warns against nested quantifiers.
- [Protego differs from Google's parser on edge cases] → The status mapping is ours and tested, and matching edge cases are pinned in pure-logic tests.
- [The Public Suffix List snapshot goes stale] → `publicsuffixlist` releases often, and the pin is updated with every release.
- [Windows delivers console control events to every process on the console] → CTRL_BREAK tests start the crawler in a new process group.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds its tables and columns to the declared schema and to `docs/schema.md` in the same slice, and `schema_version` stays 1 (015 D5).

## Interface points for later changes

- **`022`:** its timeout settings feed the watchdog function of D16, which keeps the watchdog at least 30 seconds longer than the Fetcher's total request deadline. It replaces the Fetcher implementation behind the Protocol of D8; uses the per-host gate of D7, `ScopeRules.is_internal`, the fake Fetcher and the DNS resolver hook; adds `urls` columns in its slices (`redirect_url_id` with its index `urls_redirect_url_id`), writes the `discovered_via`, `skip_reason`, `fetch_error` and `parse_error` values that this change already lists (D18), and adds its keys to `CrawlSettings`.
- **`024` (v0.2):** records a URL listed in a sitemap with `discovered_via` = `xml_sitemap` (a Link type, D5), never `sitemap`, and its sitemap files with `sitemap_input` or `sitemap_index`. All of these are already listed (D18), as is `sitemap_hreflang`.
- **`026`:** writes `parse_error` = `worker_crashed`, already listed (D18); benchmarks the engine as built; may move extractors into a pool without changing their signatures; uses the stop flag's grace period.
- **`030`:** stores every Link with this change's `LinkType` and `declared_in` (D5); adds its extractor, handler and pass to `default_hooks()`, with its row types and writers in `spider.store.pages` and `spider.store.links`; imports the robots directives parser, `DiscoveredLink` and the decoding function; adds its keys to `CrawlSettings`.
- **`040`:** adds its per-URL handler and its post-crawl pass of query Rules, with the writers in `spider.store.issues`.
- **`060`:** adds `interrupted` to `TRANSITIONS`; uses `StopReason` for `crawl_runs.stop_reason` (D18); calls the continue operation for `resume`, with its kill-then-resume scenarios; sets the `StopSignal` from control rows (`requested`); builds the `CrawlContext` in the detached process; reuses validation and config resolution (D11).

## Open Questions

These are deferrable: each would add a flag or column later without changing these specs.
- `--resolve host:port:address`, to crawl a pre-launch server under the production host name.
- Screaming Frog-style store/crawl switches per Link type, for example crawling `amphtml`.
- An opt-in cookie session, for sites that gate on a session cookie.
- Refusing External checks of private or link-local addresses, for example `169.254.169.254`, when crawling from cloud machines.
- A `robots_matched_line` column, Screaming Frog's "Matched Robots.txt Line", as a v0.2 candidate.
- Reading `<meta name="<token>">` for the robots user-agent token. `030` does not read crawler-specific meta elements in v0.1.
- A human-readable progress line when stderr is a terminal and `--format table` is used.
