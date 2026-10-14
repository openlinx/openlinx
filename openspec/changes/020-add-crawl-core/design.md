## Context

- **What this change builds on:**
  - `000-scaffold-project`: `spider.aio.loop_factory`, `spider.clock.Clock` with `SystemClock` and the test `FakeClock`, the network guard, and the fixture site with its request log and its `delay` and `hang` options.
  - The archived `010-add-workspace-and-cli-contract` (openspec/specs/workspace and cli-contract, and its design):
    - a Command is an adapter plus a service with typed inputs and a `Reporter` (`warn`, `event`); `Collected` keeps the calls in memory (010 D9)
    - partial results: a Command returns `Outcome(result, SpiderError)`, the runner prints the result, then the one error (010 D5)
    - the code registry in `spider.output.codes`, with `ExitCode.USAGE` (2), `BUSY` (5), `IO` (7), `NETWORK` (8), `INTERRUPTED` (130) and the declared `interrupted` and `invalid_value` (010 D5)
    - the settings registry: tables registered in `build_app` as `"module:Class"`, one owner per table, `None` defaults, `secret` on the settings field, flag > `spider.toml` > default (010 D2)
    - `@command_meta(name=CONST, output="document", events=True)` and `OptionMeta(setting=...)` (010 D7), the startup allowlist test (010 D10), and `spider.naming` (010 D11)
  - `015-add-crawl-store`, as merged on main (its spec is `openspec/specs/crawl-store`):
    - `spider.services.crawls.create_crawl(NewCrawl, clock, reporter)` returns a `CrawlFile(id, path)`; the `crawl` row and `seeds` are written in the file's first transaction. It chooses the journal mode from `NewCrawl.journal_setting` (`JournalSetting`: `auto`, `wal` or `delete`, default `auto`) and reports `store_wal_unavailable` through the Reporter
    - the `[store]` table, `spider.store.settings:StoreSettings` with `journal_mode`, registered in `build_app`
    - redaction: `NewCrawl.secret_names` is a required `SecretNames(flags, settings)` (in `spider.store.records`), which an adapter gets from `spider.cli.options.secret_names(command, tables)`; `create_crawl` redacts the command line and config with it before anything is written (015 D7)
    - `CrawlWriter(path, clock, on_commit=None)`: `run(unit)` and `await run_async(unit)` return the unit's result once it has run, without waiting for the commit; a unit is `Callable[[Connection], T]`; the writer commits every 500 units or 1 s, `flush()` commits at once, and `close()` commits and checkpoints. Opening and `close()` block, so they run through `asyncio.to_thread`. A writer whose thread ends raises `CrawlWriterClosedError` to every later caller, and a busy file reaches the caller as the `SpiderError` `crawl_busy` (exit 5)
    - `set_state(connection, state, at)` in `spider.store.crawls`, which sets `completed_at` only for `completed`
    - the shared column types `Timestamp`, `Json` and `Flag`, `info={"change": <n>}` and comments on every table and column, and the contract test against `docs/schema.md`
    - `CrawlState` and `CrawlMode` as `Literal`s in `spider.store.records`, which loads no sqlalchemy
- **`017-speed-up-crawl-writer`,** as merged (PR #4, merge f5abc9e):
  - `submit(unit)` and `await submit_async(unit)` return a Future resolved at the commit that holds the unit, on the caller's loop for `submit_async`, with a window of 2,000 unresolved units. Cancelling a Future never withdraws its unit.
  - A unit that only reads runs in the open transaction and commits nothing (`017` D5).
  - The optimistic batch may run a unit twice, so every unit follows `017` D7, and a unit that runs once per URL executes statements built once (`017` D9).
  - A unit that fails rolls the batch back; the writer runs the batch's earlier units again and commits them at once, and the failing unit's Future gets its own error (`017` D6). A unit that fails, or returns another result, when it runs again ends the writer: the Futures of that batch get `CrawlWriterReplayError`, and every later caller `CrawlWriterClosedError`, caused by it.
  - A unit run with `run_async()` takes no room in the window, so the frontier reads (D1) never wait behind submitted units.
  - `opening(path, *, role=...)` takes a `ConnectionRole`: `create` for `create_crawl`, `write` for the writer and `read` for readers (`017` D8).
  - The test helper `replay_now(writer)` in `tests/support/writer.py` forces a replay (docs/testing.md).
  - The writer's connection settings (temporary store in memory, 64 MiB cache, memory mapping in WAL mode).
  - `on_commit(units)` counts every unit a commit made durable, read-only units included, so this change never uses it for progress (D10).
- **`018-add-schema-conventions`,** as merged (PR #5, merge 89da89a), **and ADR-0005:**
  - every public table is declared with `public_table(name, *columns, comment=..., change=20)` in `spider.store.schema`, which makes it `STRICT` and adds a CHECK named `<table>_<column>_values` for each column with `info["values"]` and `<table>_<column>_flag` for each `Flag` column; `public_tables()` is the one filter of internal tables
  - an index is a named `Index` whose `info["description"]` says the query it serves; `spider schema` lists it (name, description, columns, unique, where), and reads `references` from declared foreign keys
  - `docs/schema.md` gives each table a section with a Columns table and an Indexes table, which `spider.services.schema_doc.parse_tables` reads; the contract test compares it with the declaration and a new file, indexes, STRICT, `WITHOUT ROWID` and CHECKs included
  - the guards over the declaration (`tests/contract/test_conventions.py`): every `_id` column is a reference, every index is named `<table>_...` and described, no public table has a `UniqueConstraint` or `unique=True` (a unique rule is a named unique index), and no column has two foreign keys. The first two pass vacuously until this change's first foreign key (task 4.5) and first index (task 4.2), whose tasks add an assertion that one was seen.
  - the schema blueprint of 2026-10-11 and its rulings decide this change's tables (D18)
- **ADR-0006 and CONTRIBUTING's Code style:** pure functions over frozen dataclasses, and frozen `msgspec.Struct`s for page preparation's per-response records, which cross `026`'s pool (`DiscoveredLink`, extractor outputs and the page-preparation record) or are built beside them in the worker (`PageInput`), D5 and D9; `slots=True` on every record made per URL or per Link (`Request`, `FetchResult`, `InvalidUrl`, `UrlResult` and the store rows); `kw_only=True` on every record of more than three fields (`CrawlContext`, the result); dependencies as Protocol-typed parameters (the `Fetcher`, the `Clock`, the `Reporter`) carried by one `CrawlContext` (D15); no class hierarchy of our own; and a broken contract inside our code raises a built-in error. `018`'s guard (`tests/test_code_style.py`) refuses a dataclass that is not frozen and a subclass of our own class, and from task 3.1 a Struct that is not frozen; the review checks the rest.
- **ADR-0001:** an own asyncio engine on aiohttp, whose frontier lives in the crawl store; the Fetcher sits behind an interface.
- **ROADMAP decisions of 2026-10-05:** no default `--max-urls`, the robustness rule, 060-min in v0.1, and four design points from the architecture review (D12–D15).
- **The split of the crawler:** this change is the core. `022` adds the fetch policy, `060`-min background Crawls and `resume`, `026` the parse pool and its benchmark, and `024` the other Crawl Modes in v0.2. Each plugs in without reworking the core.
- **The thin slice** (ROADMAP, Build order: 015 → 017 → 018 → 020 → 030-min → 040-min → 050 issues) needs from this change: normalisation, the host Scope, hyperlink discovery, a foreground Crawl that writes `urls` through the writer, `is_internal`, `fetch_error`, the result and exit codes, and the hooks that `030` and `040` plug into. tasks.md marks those groups `slice`; the rest widens.
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
- **No in-flight state:** there is no separate frontier table and no persisted "in flight" state. A URL leaves `queued` only in the writer unit that stores its response and the URLs discovered from it, or in that unit's fallback unit (D2). After a crash, anything in flight is still `queued`.
- **No in-memory URL map:** discovered URLs are inserted with `INSERT … ON CONFLICT (url) DO NOTHING` inside the URL's unit, and the unit reads back the ids it needs. The unique index `urls_url` is the only dedup, so memory does not grow with the site. What the process keeps in memory is bounded by the site's shape, not its size: the URLs in flight (at most the global cap of D7), one robots.txt verdict cache and one politeness gate per origin, the 60-second rate window, the warnings, and the URLs of the network pause's count (D16), at most `max(8, 2 × concurrency)` plus those in flight.
- **Dispatch order:** the scheduler takes queued URLs of the open Crawl Depth in batches, ordered by `urls.id`, through a writer unit that only reads, with `await writer.run_async(read)`. It runs after every unit submitted before it, so it sees their URLs; it returns once it has run, never waiting for a commit or for room in the window; and it commits nothing (`017` D5).
  - The batch read is `fetch_state = 'queued' AND crawl_depth = :depth AND id > :after ORDER BY id LIMIT :n` over the partial index `urls_crawl_depth_id` (D18). `:after` is the last id taken at that depth in this run, so a URL in flight is never taken twice.
  - The cursor starts again with each run, after a continue has re-queued URLs, so re-queued URLs with small ids are found. A cursor over the whole table, without the depth and the index, would miss them. The store benchmark measured the read flat at 1–2 ms.
  - The count of anything left at a deeper depth is such a unit too.
  - Order: SQLite gives an `INTEGER PRIMARY KEY` the next larger value and URLs are never deleted, so `id` grows in the order URLs are first recorded. It is the explicit insertion sequence that 015's conventions ask for, so no separate `seq` column is added and no timestamp is ever a tie-break.
- **Continuing:** the continue operation first re-queues URLs that ended with no response (`error`) or were blocked by an unreachable robots.txt. Those outcomes are usually transient, and this is what makes a `failed` Crawl resumable. It also inserts the `urls` row of any Seed that has none, because a process can die between creating the Crawl and recording its first unit.
- *Alternative:* a separate `frontier` table. It duplicates URL identity and needs two writes per URL. Rejected.
- *Alternative:* an in-memory URL-to-id map, as the draft had (about 100 bytes per URL, 50 MB at 500k and growing). It contradicts the flat-memory promise once `--max-urls` has no default. Rejected; `026`'s benchmark measures the index lookups instead.

### D2. One writer unit per completed URL, with its outcome at the commit
The unit is one completed URL, submitted with `await writer.submit_async(unit)` (`017`). It holds:
- the `urls` update of that URL
- the `origins` and `urls` inserts for the URLs discovered from it (D18)
- the rows its per-response handlers returned (D9)

**The URL's task ends at the submit.** `017`'s window (2,000 unresolved units) holds a submit when the writer falls behind, so a slow writer slows the fetchers and memory stays bounded. The unit's outcome arrives at its commit, on the event loop, through the Future's callback:
- **Committed:** the callback updates the progress counters (D10).
- **The unit failed on its first run with an error of one row:** the callback submits a fallback unit that records only the URL's state: `fetch_state` = `error`, `fetch_error` = `record_failed`, and the error's type and message in `fetch_error_message`.
  - The errors of one row, after unwrapping SQLAlchemy's `DBAPIError.orig`, are an allowlist:
    - `sqlite3.IntegrityError`: a CHECK, NOT NULL, UNIQUE or foreign key
    - `sqlite3.DataError`: one value too big (`SQLITE_TOOBIG`)
    - `sqlite3.InterfaceError`: a value that cannot be bound
    - any exception that is not a database error, raised by our own row code. The writer's own errors are checked first and never count as one row's: `CrawlWriterClosedError`, `CrawlWriterReplayError` and the `SpiderError` `crawl_busy`, none of which is a database error.
  - The URLs discovered from it and its handler rows are lost. A continue re-queues it with the other `error` URLs (D1).
  - It is counted in one `record_failed` warning, and in the record-failure count of D16.
  - A unit that fails on its first run never ends the Crawl by itself.
- **Not a URL's failure,** but `write_failed` (D16):
  - every other `sqlite3.DatabaseError`, `ProgrammingError` included: the file or the connection failed, not one row. A full disk, an I/O error, or a read-only or corrupt file are such errors. A full disk usually shows inside a unit, when SQLite allocates a page, not at the commit.
  - a unit that fails, or gives another result, when `017` replays it (`017` D6): the writer ends
  - a fallback unit that fails
  - a commit that fails, which fails every Future of its batch
  - `CrawlWriterReplayError` and `CrawlWriterClosedError`: when a unit run again does not reproduce its first run, `017`'s replay check ends the writer without a commit; the Futures of the open batch get `CrawlWriterReplayError`, and every later submit `CrawlWriterClosedError`. A file-level error inside a unit, such as a full disk, usually ends the writer this way rather than failing only that unit.
  - a busy file, which the writer raises as the `SpiderError` `crawl_busy`; the result reports it as it is (exit 5, D10)
- **Units may run twice** (`017` D6): a unit runs again when a later unit of its batch fails. So it follows `017` D7: it has no effect outside the writer's connection, and it writes the frozen records built before it (D14). Its statements are built once (`017` D9).
- **Cancelling:** a stop cancels the URLs' tasks (D16). A task cancelled after its submit does not withdraw its unit (`017`), so a URL whose response reached the writer is recorded. A task cancelled before its submit leaves its URL `queued`.

The writer commits every 500 units or 1 second (`015` D4), and after `017`'s replay, so a killed process loses at most about a second of work, and those URLs are still `queued`. The engine opens the writer, and closes it at the end, through `asyncio.to_thread`. No count is stored on `crawl` while the Crawl runs (`018` D6).
- *Alternative:* `await writer.run_async(unit)` per URL, as `015` offered. The URL's task would wait until its unit ran, and the result would still say nothing about the commit. Rejected.
- *Alternative:* any unit that fails ends the Crawl with `write_failed`. One bad row, for example a value that a CHECK refuses, would stop a 500k-URL Crawl. Rejected by the robustness rule.
- *Alternative:* a denylist of the SQLite codes of a failing file (FULL, IOERR, READONLY, CORRUPT, NOTADB, BUSY). An unlisted code, such as NOMEM or CANTOPEN, would pass as one URL's failure, and the Crawl would record every remaining URL as `error`. Rejected for the allowlist. The replay check of `017` already ends the writer on most file errors, but not on one in the first unit of a batch, where there is nothing to replay.

### D3. Followed URLs are dispatched depth by depth
No followed URL (an Internal URL in the Scope) at depth d+1 starts until every followed URL at depth ≤ d has been processed. Checks, meaning External URLs, URLs outside the Scope and Resources, never block that barrier. Crawl Depth is then exact however responses interleave.
- **Processed** means that the URL's unit was submitted, or that the URL was recorded without a request. The next depth's first frontier read is a writer unit, so it runs after every unit submitted before it and sees the URLs they discovered. The barrier never waits for a commit.
- **Redirects:** `022`'s redirect targets inherit their source's depth and join the depth that is still open, so the barrier stays exact with zero-weight edges.
- *Alternative:* free order with depth lowering. Descendants of a URL whose depth was lowered late keep a wrong depth. Rejected.
- **Cost:** a stall at each boundary until the slowest internal Page of that depth is processed, bounded by the request timeout and the watchdog.

### D4. The Scope model
- **`ScopeRules`** is a frozen dataclass built once from the Seed and the settings, with a pure method from a `NormalizedUrl` to `is_internal`, `in_scope` and an optional skip reason. The host rule (`host`, `subdomains` or `subfolder`) matches on the host only, any scheme and any port. `--include`/`--exclude` come after it, and exclude wins.
- **Seed hosts and the www rule:** the Seed's host, plus `www.<host>` when the Seed's host is a registrable domain. One direction only: a `www.` Seed never admits the apex, because the reverse would quietly widen a Crawl to a host the user did not name. An IP address or a host without a registrable domain gets no `www.` host. A table-driven test of about 20 Seed/URL cases pins the rule: apex, `www.`, other subdomains, ports, IDN hosts, public suffixes such as `co.uk`, IP addresses, single-label hosts and upper case.
- **`seed_base_mismatch`:** decided from the Seed's parsed Links (its `canonical`, and the hosts of its `hyperlink` Links), once, after the Seed is recorded. It warns; it never changes the Scope.
- **Spellings of one host** (ruling of 2026-10-11): hosts are compared ignoring one trailing dot on either side, so a Seed `site.test.` makes `site.test` internal and the reverse, and the same holds for the www host, because DNS treats both as one name; the URLs stay distinct rows. IPv4 forms such as `127.1` or `0x7f.0.0.1` are not canonicalised, as aiohttp does not canonicalise them, so they are internal only when they equal the Seed host as written.
- **Registrable domains** come from `publicsuffixlist`, which ships the list and never downloads it.
  - `_registrable_domain(host)` in `spider.crawl.scope` (private until a later slice, such as `seed_base_mismatch`'s, imports it) is a pure function memoised with `lru_cache(maxsize=1024)`, over a loader of the bundled list memoised with `lru_cache(maxsize=1)` (ruling of 2026-10-11). Parsing the list takes about 56 ms and the parsed list pickles to about 175 KB, so `ScopeRules` holds only strings and stays cheap to pickle with page preparation's settings snapshot, which `026` sends to each worker once (D9). IP addresses and single-label hosts never reach the list, which would call `0.1` the registrable domain of `127.0.0.1`.
  - *Alternative:* `tldextract`. It downloads on first use unless configured otherwise, which is surprising network traffic for a tool without telemetry. Rejected.
- **Flag shape:** one enum plus the `--subdomains` shorthand that ROADMAP names.
  - *Alternative:* orthogonal flags. They double the combinations to test for the rare "subfolder on every subdomain" case, which `--scope subdomains --include` already covers. Rejected.
- **`--exclude` means never requested,** because it exists to keep a Crawl away from logout links, cart actions and calendars. **`--include` makes a Section Crawl**, whose outside URLs are checked but not followed.

### D5. Request versus parse, and the Link type table
Two independent decisions:
- **Request** depends on the Link type table, nofollow, the Scope, robots.txt and the limits.
- **Parse** depends only on the URL being in the Scope with a 2xx HTML response. A Resource Link that returns in-Scope HTML is therefore parsed, and is not a Resource under the glossary.

**The link extractor** is ours. It parses the HTML once with selectolax's lexbor backend, `selectolax.lexbor.LexborHTMLParser`; selectolax 1.0 removed the old `selectolax.parser` backend. It produces:
- `DiscoveredLink` values (frozen msgspec structs, each built once): type, normalised target, raw value, element, attribute, rel tokens, nofollow, where it was declared (`declared_in`: `html` or `http_header`, the name of `030`'s column; `origin` means scheme, host and port only, ADR-0005 rule 9), its `ordinal`, and `is_internal`, its target's Internal flag, so `030` counts outlinks without a query
  - **A reference gives no Link** when it is malformed, cannot be resolved or normalised, or its scheme is not http or https (spec, "Link discovery"), so the target is never null. `030` stores no raw `href`; if it ever needs the raw value of a dropped reference, it reads it from the same parsed tree.
  - **`ordinal`** is the Link's position in its response, from 1, in document order: the value of `030`'s `links` key `(source_url_id, ordinal)`. It is not `030`'s `link_position` (head, navigation, content, …). Task 7.9 numbers the Links of the HTTP `Link` and `Refresh` headers first, in the order received, and the HTML Links after them, as `030`'s `ordinal` does.
  - **Resolution follows the URL Standard** (ruling of 2026-10-14, task 3.8), so a recorded URL is the one a browser requests: in http and https URLs a backslash before the query is a slash, any run of slashes and backslashes after the scheme or at the start of a relative reference introduces the host, a scheme other than the base's names a host (`https:cdn.test/x`), and an empty host gives no Link. On a Page decoded as neither UTF-8 nor UTF-16, the query is percent-encoded in the Page's encoding (`query_codec` in `spider.crawl.decoding`), and a character it cannot hold becomes `&#NNNN;`; the path stays UTF-8.
  - **`is_internal`:** the extractor takes a keyword parameter `is_internal: Callable[[NormalizedUrl], bool]` and imports nothing of `spider.crawl.scope`. Page preparation passes a function over `ScopeRules.decide` from its settings snapshot (D9); seam-4 tests pass a plain function.
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
3. a `<meta charset>` or `<meta http-equiv="Content-Type">` declaration in the first 1024 bytes, as `030` lists it
4. otherwise UTF-8, falling back to windows-1252 when the body is not valid UTF-8

`030` documents the same order for text, and both go through one shared function, `decode_html` in `spider.crawl.decoding`, which returns the text and the encoding's name in the Encoding Standard (`windows-1251`, as `030`'s `page_sources.encoding` stores it).
- **Labels** are the Encoding Standard's own table (its `encodings.json`), not Python's codec names: `iso-8859-1`, `latin1` and `ascii` are windows-1252, `iso-8859-9` is windows-1254, `x-sjis` is Shift_JIS, and GBK, Big5, Shift_JIS and EUC-KR decode with the Standard's supersets. A label outside the table (`nonsense`, or Python-only names such as `u8` and `base64`) is skipped, and the next source applies; so are `x-user-defined` and the replacement encoding's labels, which have no Python codec.
- **The `<meta>` prescan** reads `<meta>` elements outside comments, in order: a `charset` attribute, or `http-equiv="Content-Type"` with a `charset=` in `content`. A label outside the table moves on to the next `<meta>`. It is a regex approximation of HTML's prescan, bounded by the 1024 bytes.
- **A `<meta>` declaration of UTF-16** means UTF-8, as the Standard says, since the bytes it was read from were ASCII.

### D6. robots.txt and the robots directives
- **Parsing:** Protego parses robots.txt, and the verdicts are cached per origin for the run. Only the first 512,000 bytes are parsed, decoded as UTF-8 with replacement.
- **Status mapping:** the RFC 9309 mapping (2xx `ok`, 4xx except 429 `missing`, 5xx/429/no response `unreachable`, more than 5 redirects `missing`) is a pure function.
- **No HTTP response** (ruling of 2026-10-14): 5xx and 429 disallow the origin, and its URLs are `skipped` with `robots_unreachable`, as RFC 9309 says. A robots.txt request that gets no HTTP response at all says the origin cannot be reached, so each URL of the origin is recorded as `error` with that request's `fetch_error` (`dns_error`, `connection_refused`, …, and `022`'s `timeout` and `tls_error`), without a request of its own, and a `fetch_error_message` that names the robots.txt request; `robots_state` stays `unreachable`, with `robots_status_code` NULL and the request's error in `origins.robots_fetch_error` and `robots_fetch_error_message` (ADR-0005's error code and message, with the value set of `urls.fetch_error`), so an agent sees why without a join to `urls`.
  - Why: recorded as `robots_unreachable`, a dead External domain would read as a robots.txt problem, and "An unknown host is a DNS error" contradicted the old mapping.
  - On an Internal origin each such URL counts toward the network pause (D16), unless its code is `tls_error`. A continue re-queues them with the other `error` URLs (D1).
  - The Seed's origin is the exception: until it has answered, its robots.txt without a response pauses the Crawl (D16), and the robots.txt request is made again when a probe answers.
- **The robots.txt request** follows its own redirects internally, up to 5 hops. It goes through the same politeness gate and counts for `--rate`, but not for `--max-urls`.
- **Crawl-delay** is recorded, not applied, which matches Googlebot and Screaming Frog.
- **The robots directives parser** is a pure function from meta `content` values, `X-Robots-Tag` header values and the robots token to the directive values, named as `030`'s columns (`meta_robots_noindex`, `x_robots_tag_nofollow`, …). `030` imports it, so the two changes can never disagree about noindex or nofollow.

### D7. Politeness
- **Per-host limits:** a semaphore per host (`--concurrency`) and a per-host "next allowed start" time (`--rate`).
- **Global cap:** 4 × concurrency, clamped to 20–100, bounds sockets when many External hosts are checked.
- **Clock:** all waiting goes through the context's `Clock` (`monotonic()`, `sleep()`), including the watchdog, the network pause's probes and the stop grace period (D16), so `FakeClock` drives every timing scenario.
- **Blocking detection:** a counter of consecutive 403/429 responses per Internal host.
- `022` adds retry backoff and `Retry-After` pauses on the same per-host gate.

### D8. The minimal Fetcher
- **The interface:** a `Fetcher` Protocol, `async def fetch(self, request: Request) -> FetchResult | FetchFailure`, over frozen dataclasses with `slots=True`, made once per request, and `kw_only=True` above three fields (ADR-0006). It makes exactly one hop and never follows redirects. `022` replaces the implementation without changing the Protocol.
- **The aiohttp implementation in this change:**
  - raw response headers in order and letter case
  - a fixed 20-second total timeout, which `022` makes configurable
  - aiohttp's default TLS context, which `022` replaces with truststore
  - a DNS resolver hook (an aiohttp resolver), which tests use to map host names to fixture instances
- **Errors** are returned as a `FetchFailure` (its `fetch_error`, a message, `fetched_at`; review of group 5), never raised: name resolution, and a name the system resolver cannot encode such as `a..b.test`, → `dns_error`, `ConnectionRefusedError` → `connection_refused`, protocol errors → `invalid_response`, and every other exception of the request, a reset included → `connection_error`, with the exception type in `fetch_error_message`. Only cancellation passes through.

### D9. Hooks and the extractor registry
- **`Hooks`** is a frozen dataclass of tuples, part of the Crawl context (D15): extractors, per-response handlers and post-crawl passes. `default_hooks()` in `spider.crawl.hooks` lists the built-in ones explicitly, with no plugin discovery; `030` and `040` add theirs to that list. A test passes `default_hooks()` plus its own entries to the Crawl Service, so nothing registered for one test leaks into another.
- **Extractors** are pure: a name and a module-level function from the parsed tree and a frozen `PageInput` to a msgspec struct. They are module-level so that a worker process can import them by name.
  - `PageInput` holds what page preparation already has besides the tree: the response URL, status and headers, the decoded document's length, the `DiscoveredLink` values, the robots directives and the settings snapshot. `030`'s Page extractor needs all of them (canonicals from headers, Text Ratio, the Content Area).
  - It is a msgspec struct of plain values and frozen structs. Page preparation builds it and hands it to the extractors in the same process, so it never crosses a process boundary, and its settings snapshot is a reference to the one the process already holds, not a copy.
- **The settings snapshot** is frozen and built once per Crawl: the robots token, `--strip-params`, the Scope, and the settings that registered extractors read, such as `030`'s `content_area`. The in-process executor holds it. `026`'s pool passes it to each worker process once, as an argument the worker process starts with; it is never pickled with a response.
- **Page preparation** is one pure, module-level function of a fetched response (its bytes, headers and URL) and the settings snapshot of its process.
  - It decodes (D5), parses once, runs the link extractor, which normalises the discovered targets and drops the references it cannot use, then the registered extractors and the robots directives parser, and returns one frozen msgspec record.
  - An extractor that raises is caught inside it, and the record carries the `parse_error` of D16. The link extractor never raises, so the record keeps its Links, and the other extractors' outputs.
- **The executor seam:** the engine calls page preparation through an executor in the `CrawlContext` (D15), `await prepare(response)`.
  - This change ships the in-process executor.
  - `026` (v0.1, unconditional) plugs a process pool in behind the same seam without touching the engine. Per response, only the response goes to a worker and the prepared record comes back; msgspec records cross the process boundary as they are.
- **Per-response handlers** are pure too: a name and a function from a `UrlResult`, a frozen dataclass with slots (the URL's row values, and for a `fetched` URL its status, headers and extractor outputs) to a sequence of store rows (D14). They run for every URL that reaches a final state, including `error` and `skipped`, so `030` can record cookies on any status.
- **Post-crawl passes** run when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written. A pass is a store function (D14) that submits its own units, so a pass over 500k Pages can write in batches. `030` computes inlink counts there, and `040` materialises its Rules' Issues by their queries. `040` also relies on the passes running before `completed` or `stopped` is written: those two states tell it that a Crawl's Issues are materialised. Passes run again after every continued run, so they must be safe to re-run, and they never run for a `failed` Crawl or a killed process.
- *Alternative:* module-level registries, as the draft had. Tests that register into them leak into each other. Rejected.
- *Alternative:* "sinks" that turn extractor structs into rows. They are handlers by another name. Merged into handlers.
- *Alternative:* the engine calls each extractor itself. A pool would then need the parsed tree in the worker process, and a tree cannot cross a process boundary. Rejected.

### D10. Events, result, exit codes and interrupts
- **Events and diagnostics** go through the context's `Reporter`. The Crawl Service wraps it in a warning log that writes each warning once per code and host, keeps it for the result and `crawl.warnings`, and adds `details.count` and `details.first_url` to counted warnings (D16). `progress` is fixed at every 10 seconds, and goes on during a network pause with `paused` = true (D16). `crawl_paused` and `crawl_resumed` mark a pause. Its `urls` counts come from counters that the callbacks of D2 update as units commit. Progress never uses the writer's `on_commit`, which counts read-only units too: the frontier reads (D1) are writer units that join the batch. They are seeded once per run by a counting query over `urls`, so a continued Crawl starts from its earlier counts. No count over `urls` runs for each event, because a `GROUP BY fetch_state` scans the table (ruling Q1, D18).
- **The result** is a frozen dataclass with `kw_only=True` and `to_json()`, built at the end from counting queries over `urls`, never from in-memory counters. The adapter returns it, or `Outcome(result, SpiderError)` for a failed outcome, so `010`'s runner prints it before the one error:
  - `interrupted` (declared by `010`) → exit 130
  - `seed_unreachable` and `site_unreachable`, after the network pause has waited `--network-wait` (D16) → exit 8
  - `crawl_write_failed` → exit 7, or `015`'s `crawl_busy` → exit 5, as the writer raised it
- **Interrupts:**
  - The Crawl runs under `asyncio.Runner(loop_factory=loop_factory)`. `signal.signal` handles SIGINT (plus SIGBREAK on Windows, and SIGTERM/SIGHUP on POSIX) and sets the stop flag through `loop.call_soon_threadsafe`, because Windows loops have no `add_signal_handler`. So no `KeyboardInterrupt` reaches `010`'s runner during a Crawl.
  - The stop flag is a `StopSignal` in the context: it is set once, with the `stop_reason` the Crawl ends with. `060`'s control rows set the same object.
  - A second interrupt calls `os._exit(130)`. The last committed unit keeps the store consistent (D1).

### D11. Settings and the recorded config
- **The `[crawl]` table** is owned by this change: a pydantic model `CrawlSettings` in `spider.crawl.settings`, registered in `build_app` as `("crawl", "spider.crawl.settings:CrawlSettings")`. It follows `010`'s table rules; `max_urls`, `max_depth` and `rate` default to `None` (written `# max_urls =` in the template), which means "no limit", and `network_wait` (D16) defaults to 1800 seconds, with 0 allowed and a negative value refused as `invalid_value`. `022` and `030` add their keys to this model; they never register a second table.
- **No inert option** (ruling of 2026-10-14): an option and its setting are declared by the task that applies them, so main never has a flag that is accepted and ignored, such as a `--max-urls` that would let a Crawl run unbounded. `[crawl]` starts with `concurrency` (task 4.11); `max_depth`, `max_urls` and `rate` come with tasks 9.5, 9.7 and 11.1.
- **Options** declare `OptionMeta(setting="crawl.<key>")`, so `spider commands` lists each option's setting and default, and the scenario "The recorded config holds every registered crawl setting" stays generic. `--subdomains` has no setting: the adapter resolves it into `scope` before loading settings.
- **The recorded config** is the resolved value of every registered table, `[crawl]` and `015`'s `[store]` included, as `NewCrawl.config`. The Crawl Service loads settings once and builds both the `NewCrawl` and the context from them.
- **The journal mode (`015` group 8, built):** the Crawl Service sets `NewCrawl.journal_setting` from the resolved `[store] journal_mode`, in the slice. `create_crawl` reports `store_wal_unavailable` through the Crawl Service's warning log (D10), so it reaches the result and `crawl.warnings` like any other warning.
- **Redaction (`015` group 9, built):** `NewCrawl.secret_names` has no default, so the slice passes it from the start. The `crawl` adapter calls `secret_names(<its Click command>, <the settings tables>)` and hands the result to the Crawl Service, which puts it in the `NewCrawl`; `create_crawl` redacts by itself. `[crawl]` has no secret setting in v0.1, so nothing of it is redacted yet; `022` (v0.2) adds secret ones.
- **Validation and config resolution** are one function the adapter calls before anything is created, so `060`'s detached start and dry run reuse it and cannot disagree with a foreground Crawl.

### D12. Crawl State transitions
- **The table:** `TRANSITIONS` maps each allowed `(from, to)` pair to the `stop_reason` values it allows: `running` → `completed` (none), `running` → `stopped` (`max_urls`, `interrupt`, `requested`), `running` → `failed` (`seed_unreachable`, `site_unreachable`, `write_failed`), and `stopped` | `failed` → `running` (none). `StopReason` is a `Literal` next to `CrawlState` in `spider.store.records`, so `015`'s `values` mechanism documents the column from it.
- **The check:** one pure function, `check_transition(current, target, stop_reason)`, raises `CrawlStateError`, a `RuntimeError`, for anything else. It is a bug in the caller (CONTRIBUTING, Code style), so it reaches the agent as `internal_error` (exit 70), never as a quiet wrong state.
- **One writer of the end of a Crawl:** `015`'s `set_state(connection, state, at)` gains the `stop_reason`, reads the current state on the same connection, inside the caller's unit, runs the check, and writes `state`, `stop_reason` and `completed_at` together. Nothing else writes those columns.
- **`060`** adds `running` → `interrupted` and `interrupted` → `running` to the table, and records `interrupted` from another process through the same unit.
- *Alternative:* a state-machine library. One dict and one function are enough, and stay readable in `docs/crawling.md`. Rejected.

### D13. URL types
- **`NormalizedUrl = NewType("NormalizedUrl", str)`** in `spider.crawl.urls`, a leaf module that imports nothing else of `spider`, so the store's row types can use it too. Only the normaliser returns it; the store's reads of `urls.url` cast to it, in one place each. mypy then refuses a raw `str` wherever the frontier, `ScopeRules`, `DiscoveredLink` or the store rows expect a normalised URL. A guard in `tests/test_code_style.py` keeps both rules (task 1.16): the module imports nothing of `spider`, and `NormalizedUrl(` is called only by the modules on its allowlist, to which each store module that casts `urls.url` adds itself.
- **The normaliser never raises:** it returns `NormalizedUrl | InvalidUrl`, where `InvalidUrl` is a frozen dataclass with slots (ADR-0006) and the reason. The Seed parser maps it to `invalid_url`; the link extractor drops the reference, which gives no Link (D5).
- **Hosts are encoded as aiohttp encodes them** (ruling of 2026-10-11), because the host recorded must be the host aiohttp requests: an ASCII host is only lower-cased, an IP address takes its compressed form, and any other host goes through the `idna` package with UTS46 (non-transitional, as browsers do), falling back to Python's IDNA 2003 codec as aiohttp's URL library does. The code points UTS46 deletes silently are refused. Python's codec alone would turn `faß.test` into `fass.test`, a host the link does not name. A hypothesis property checks that every host the normaliser accepts equals aiohttp's.
- **A URL with userinfo is rejected** (ruling of 2026-10-11), as `InvalidUrl("userinfo")`: kept, its credentials would be recorded in `urls.url`, which `015`'s redaction does not cover, and sent with every request; dropped, `https://user@site.test/` would silently become another URL, and the Seed `mailto:a@b.test` would become `https://b.test/`. A Seed with userinfo is `invalid_url`, whose hint names `022`'s `--auth`; a Link with userinfo is dropped like a malformed reference.
- **A Seed's scheme** (ruling of 2026-10-11) is an RFC 3986 scheme name followed by `:`, unless a port follows the `:` (digits, then `/`, `?`, `#` or the end): `site.test:8080/x` and `localhost:8080` have none and get `https://`, while `mailto:`, `tel:`, `javascript:` and `ftp:` are schemes, refused as not http or https. Testing only for `://` read the Seed `http:` as the host `http`, and `mailto:a@b.test` as a user name before the host `b.test`. By the rule, `tel:123` stays the host `tel` with port 123, as `localhost:8080` is a host and a port.
- **Speed** (rulings of 2026-10-11): the normaliser runs for every Link of every Page, about 466 per Page. Measured on distinct URLs, it took 9 µs for a typical ASCII URL, 51 µs for one on an IDN host and 191 µs for a long non-ASCII path. Three changes, each guarded by properties (tasks 1.17–1.19): a URL already in normal form passes through one regex unchanged; existing percent-encodings are normalised before new ones are written; and the host encoder, a pure function, keeps a bounded `functools.lru_cache`, since a site's hosts repeat and every internal URL of a `.рф` site is IDN. A bounded memo of a pure function has no visible behaviour, so it is not the module-level state ADR-0006 rules out.
- *Alternative:* a frozen class with parsed parts. It allocates per URL on the hottest path (every Link of every Page), and every SQL boundary would convert it back to text. Rejected; the host and origin are derived with small pure functions where they are needed.
- **Crawl ids stay `str`.** They are created and validated in one place each (`015`'s `new_crawl_id` and `is_crawl_id`), flow through `CrawlFile`, and are never mixed with URLs. A `CrawlId` type is worth it when `060` accepts ids from users; that change decides it.

### D14. Data access stays in the store
- **The rule:** writer units are defined only in `spider.store.*` modules. The engine, the extractors and the Rules build frozen values and call store functions that return units; they never write SQL. A guard in `tests/test_code_style.py`, next to `018`'s ADR-0006 guard, reads every module of `src/spider` with `ast` and names each one outside `spider/store/` and `spider/services/schema.py` (which imports it lazily) that imports `sqlalchemy`, at module level or inside a function. `010`'s startup allowlist test stays as it is.
  - *Alternative:* ruff's banned-API rule (`TID251`) on `sqlalchemy`, with per-file ignores. It applies to the whole repository, and the tests and `scripts/writer_throughput.py` import `sqlalchemy`. A per-file ignore of `TID251` for them would also lift the bans that `TID251` already carries there: asyncio's loop policies and Typer's vendored Click (CONTRIBUTING, Code style). Rejected.
- **This change's store modules:** `spider.store.urls` (the units of the `urls` table, whose declaration is in `spider.store.schema` with every public table: recording a Seed, the next batch, recording a completed URL with its discovered URLs and handler rows, re-queueing on continue, and the counts), `spider.store.origins` (the units of `origins`: an origin's row, recorded in the unit of its first URL, and its robots.txt), and `spider.store.crawls` (`set_state`, the Scope and the warnings).
- **Units follow `017` D7:** a unit is deterministic given the file's state and its frozen input, so running it again after a later unit fails gives the same result and changes the same rows. It has no effect outside the writer's connection, and it returns values only (ints, tuples, frozen dataclasses), never live objects. `017`'s replay check ends the writer when a unit breaks this (D2). Seam-2 tests of each store module check it with `017`'s `replay_now(writer)` test helper (`tests/support/writer.py`), which forces a replay.
- **How `030` and `040` add theirs:**
  - **Rows:** a handler returns store rows: frozen dataclasses with `slots=True` (ADR-0006: one or more per URL) declared in a module of `spider.store` that loads no sqlalchemy, as `spider.store.records` does today. The store module that owns the table registers the function that writes each row type, and the URL's unit writes the rows it is given through those functions. So `030` adds `spider.store.pages` and `spider.store.links`, and `040` adds `spider.store.issues`.
  - **Passes:** a post-crawl pass is itself a store function, for example `030`'s inlink counts in `spider.store.links` and `040`'s query Rules in `spider.store.issues`.
- *Alternative:* handlers that get the `Connection`. Every later change would then write SQL from extractors and Rules, which this rule exists to prevent. Rejected.

### D15. One context for a Crawl's dependencies
- **`CrawlContext`** is a frozen dataclass with `kw_only=True` (ADR-0006): the `CrawlFile`, the resolved `CrawlSettings`, the `ScopeRules`, the `Clock`, the `Reporter` (the warning log of D10), the `CrawlWriter`, the `Fetcher`, the page executor (D9), the `Hooks` and the `StopSignal`.
- **Built in one place:** an async context manager in the Crawl Service opens the writer, the Fetcher's session and the page executor, yields the context, and closes them, the writer through `asyncio.to_thread`. The start and continue operations use it; `060` uses it for detached Crawls.
- **Who takes it:** only the imperative shell (the engine, the scheduler, the robots.txt loader and the service). The pure modules (normalisation, Scope, robots, directives, extraction, transitions) take plain values, so they stay table-testable at seam 4.
- **Boundary doubles go in through it:** tests pass a fake Fetcher, `FakeClock` or the DNS resolver hook to the builder. Nothing else of ours is replaced.
- *Alternative:* growing every signature with each dependency. `022` alone would touch most of the engine. Rejected.

### D16. Robustness and backstops
- **Parsers never raise:** the Seed parser, the normaliser, decoding, the link extractor, the directives parser and the robots.txt reader return their result or their own rejection type. Each has a hypothesis property over arbitrary input (bytes, text, malformed HTML) that it never raises, next to its table tests.
- **The engine still contains** an extractor or handler that raises: the extractor's failure becomes `parse_error` = `extractor_error`, with `<name>: <type>` in `parse_error_message`, while the URL keeps `parsed` = 1, its Links are followed and handlers get the other outputs (ruling of 2026-10-14: a bug in one extractor that fires on every Page must not stop discovery at the Seed and silently truncate a Crawl; `parsed` = 0 is for a response nothing came out of), the handler's drops only its rows, and each is counted in one warning (`parse_failed`, `handler_failed`). A unit that fails on its first run with an error of one row is recorded through a fallback unit as `record_failed`, counted in one `record_failed` warning (D2).
- **Recording keeps failing:** a count of URL units in a row that failed on their first run with an error of one row (D2). A URL unit that commits resets it, and fallback units do not count. At `RECORD_FAILURE_LIMIT` (100), a named constant, the stop flag is set with `write_failed`.
  - Why: D2's allowlist cannot tell one bad row from a bug in our own row code that fails for every Page, such as a `TypeError`. That bug would turn a 500k-URL Crawl into `error` rows.
  - Why 100: real bad rows are rare and independent of each other, so 100 in a row with no success between them is a bug. 100 URLs are also little to lose next to a Crawl.
  - It has the shape of the network pause's count below.
- **The network pause** (ruling of 2026-10-14; it replaces failing at once when the site is lost): a counter of consecutive Internal requests without an HTTP response; any response resets it.
  - **What counts:** the `fetch_error` codes `dns_error`, `connection_refused`, `connection_error`, `invalid_response` and `watchdog`, `022`'s `timeout`, and the URLs recorded from an Internal origin's robots.txt without a response (D6). `022`'s `tls_error` does not count: a certificate failure is an answer of sorts, and a site-wide one must not wait `--network-wait` and then fail with a misleading `site_unreachable`.
  - **Pausing:** at `max(8, 2 × concurrency)` the Crawl pauses. No request starts; requests in flight finish. One that gets a response is recorded; one that ends without one is not recorded, so its URL stays `queued`, and the engine requests it again when the Crawl resumes (the depth cursor of D1 has already passed it).
  - **Probes:** the Seed URL, through the per-host gate (D7), at 5, 10, 20 and 40 seconds after the pause began and then every 60 seconds, waiting on the context's `Clock`. One pure function gives the probe times for a `--network-wait`, tested at seam 4. A probe is not recorded and does not count toward `--max-urls`.
  - **Outcomes:** the first probe answers (any status) → a dead section: the failures were the site's own, so the Crawl resumes and keeps their errors. A later probe answers → an outage: the engine re-queues the URLs of the count, each at most once in a run (a set of the URL ids re-queued in the run), dispatches them ahead of the frontier read, and resumes. No probe that starts within `--network-wait` answers → the stop flag is set with `site_unreachable`; `failed` stays resumable, and continuing re-queues the `error` URLs (D1). With `--network-wait 0` no probe starts.
  - **The Seed at the start:** until the Seed's origin has given an HTTP response, its robots.txt or Seed request without one pauses at once, since a network may come up or switch just as a Crawl starts (a VPN). An answering probe re-requests the robots.txt and the Seed; no answer within `--network-wait` sets the stop flag with `seed_unreachable`.
  - **Visibility:** `crawl_paused` (`reason`, the `fetch_error` that tripped it, and `urls`, the count's URLs) and `crawl_resumed` (`duration_s`, `outcome` `outage` or `dead_section`) events; `progress` events go on with `paused` = true; one counted `network_paused` warning with `details.count` (pauses) and `details.total_seconds`. `060` shows `paused_since` from the same state.
  - **A stop** (the URL limit, an interrupt or `060`'s stop request) ends a pause like any other wait.
  - Why: failing a 500k-URL Crawl when a laptop's Wi-Fi drops for a minute, or a VPN switches, wastes the run, and recording the rest of the site as errors is worse. A pause with probes tells an outage from a dead section of the site without a setting per case. It generalises the zero-success breaker of the architecture review.
  - *Alternative:* fail at once with `site_unreachable`, as the earlier design did. A short outage then ends the Crawl, which an agent has to notice and resume. Rejected by the user on 2026-10-14.
- **The watchdog:** each request races `clock.sleep(watchdog_seconds)`; the loser is cancelled, and a cancelled request is recorded as `fetch_error` = `watchdog`. One pure function computes `watchdog_seconds` from the settings: `max(120, the Fetcher's total request deadline + 30)`. In this change the deadline is the fixed 20 seconds of D8, so the watchdog is 120 seconds; `022`-min's timeout settings feed the same function, so a watchdog never cuts a slow response that the Fetcher still allows. It is a backstop behind the Fetcher's own timeout, for a hang that the timeout does not cover. A request ended by the watchdog counts as one without an HTTP response for the network pause.
- **Stop:** grace then cancellation. After the stop flag is set, no request starts; requests in flight get 10 seconds of clock time, then are cancelled before their submit, so their URLs stay `queued`. A URL whose unit was already submitted is recorded, because cancelling never withdraws a unit (`017`).
- **Writing fails:** a unit fails with an error that is not of one row, a unit fails or differs in `017`'s replay, a fallback unit fails, a commit fails, the writer has ended, or recording keeps failing (D2, above). The engine sets the stop flag with `write_failed`, and the service tries once to record the end through a fresh writer. A second failure leaves the file `running`, which `060` reports as `interrupted`.
- **Hostile fixtures** added by this change: a connection reset in the body, deeply nested HTML, bytes invalid in their declared charset, and 429 and 503 robots.txt. `022` adds the stalled, trickling, huge and compressed ones with its limits.

### D17. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, each by the slice that first raises it:
- errors, exit 2: `invalid_url`, `option_conflict`, `subfolder_is_root`, `invalid_pattern`, `seed_out_of_scope`
- errors, exit 8: `seed_unreachable`, `site_unreachable`
- error, exit 7: `crawl_write_failed`
- warnings: `seed_blocked_by_robots_txt`, `robots_unreachable`, `possible_blocking`, `max_urls_reached`, `seed_base_mismatch`, `parse_failed`, `handler_failed`, `record_failed`, `network_paused`

`interrupted` and `invalid_value` come from `010`, and `crawl_busy` from `015`. Hints that name a Command use `spider.naming`.

### D18. The tables under ADR-0005
The schema blueprint of 2026-10-11 and its rulings decide `urls`, `origins` and the new `crawl` columns before they are built. `018`'s `public_table()`, its guards and its contract test enforce what a test can; the review checks the rest of ADR-0005.
- **Declaration:** each table is declared with `public_table(..., change=20)` (`018`), so it is `STRICT`, and its enumerations and flags get CHECKs from `info["values"]` and the `Flag` type. No column of this change is derived or filled by a later release, so none carries the `Derived: ` or `Filled from ` prefix.
- **Every value from v0.1:** each enumeration lists the values that `022`, `024` (v0.2) and `026` will write (spec, "The urls table").
  - A CHECK that changes after v0.1 is a schema change with a migration. One that changes inside v0.1 would still make three other changes modify this change's spec.
  - The lists are `Literal`s in `spider.store.records`, so the code, the CHECK and `values` cannot disagree.
- **Names** (ADR-0005 rules 9 and 10):
  - "Blocked by robots.txt" is `blocked_by_robots_txt` in the flag, in `skip_reason` and in the warning `seed_blocked_by_robots_txt`, as in `030`'s Indexability Status and `040`'s Rule id.
  - `parse_error` is a code, with its text in `parse_error_message`, like `fetch_error`. Its values include `026`'s `worker_crashed` and `parse_timeout` (a Page whose preparation passes `026`'s per-Page deadline; ruling of 2026-10-14), so `026` adds no value of its own.
- **`urls.origin_id`** (ruling Q4) is a declared reference, NOT NULL, so every `urls` row joins `origins`.
  - `origins` therefore holds the origin of every recorded URL, not only of requested ones. The unit that records a URL inserts its origin with `ON CONFLICT (origin) DO NOTHING` and reads back the id, as it does for URLs (D1).
  - An origin none of whose URLs was requested has no robots.txt yet, so `robots_state` and `robots_sitemaps` are nullable.
- **`urls.host` stays:** the politeness limits and the Scope work per host, not per origin (one host serves both http and https), and the scheduler needs the host of every URL it takes.
- **Indexes,** each a named `Index` called `<table>_<columns>`, whose `info["description"]` and its row in the table's Indexes table of `docs/schema.md` say the query it serves:
  - `urls_url` and `origins_origin`, unique, for `ON CONFLICT` and lookups. They are declared as named unique indexes, not as UNIQUE column constraints, because SQLite's automatic indexes for those have no name or description of ours. `018`'s guard refuses a `UniqueConstraint` or `unique=True` on a public table.
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
- **Store contract (6):** `docs/schema.md` gains every column and index in the same commit as the slice that adds it, a column in its table section's Columns table and an index in its Indexes table, so the contract test (`015`'s, which `018` extends to indexes, STRICT, `WITHOUT ROWID` and CHECKs) never goes red.

Boundary doubles used, all from the approved list:
- **The fake Fetcher and `FakeClock`:** for rate spacing, Crawl-delay, the progress interval, the watchdog and the stop grace period only.
- **The DNS resolver hook:** for the multi-host scenarios.
- **A full disk:** SQLite's own `max_page_count` limit, set by a test-scoped connection listener, so SQLite reports `SQLITE_FULL` exactly as for a full disk. No file-system fake.

## Risks / Trade-offs

- [Depth barrier stalls on a slow internal Page] → Checks never block the barrier, and the stall is bounded by the request timeout and the watchdog.
- [SQLite write throughput once `030` adds tens of millions of Link rows, plus a unique-index lookup per discovered URL (D1)] → Batched units through `017`'s writer (the optimistic batch and its connection settings) in WAL mode, the partial frontier index instead of a composite one (D18), measured by `026`'s 500k benchmark, which is also the soak test of the robustness rule.
- [In rollback-journal mode (UNC paths, `store.journal_mode = "delete"`), a long read can hold the writer for its 30 s busy timeout and fail the Crawl with `crawl_busy`] → Readers open per operation and are brief; the Crawl is `failed` and resumable; `docs/crawling.md` says to avoid long queries during a Crawl on a network folder.
- [lexbor's tree builder is super-linear in nested block elements: parsing `<div>` nested 1,000 deep took 0.6 ms, 4,000 deep 7 ms, 10,000 deep 46 ms, 20,000 deep 0.44 s, 40,000 deep 2.1 s and 100,000 deep about 80 s (`<section>` alike), while `<span>`, `<b>`, `<p>`, `<li>` and `<table>` 20,000 deep took 2–4 ms; until `026` lands, the in-process executor blocks the event loop for that long, and every request in flight can reach the Fetcher's timeout] → Ruling of 2026-10-14: `026` gives each Page's preparation a deadline, kills and replaces the worker, and records `parse_error` = `parse_timeout`. Task 5.8's fixture nests 10,000 `<div>` elements, and the link extractor's seam-4 fixture nests 100,000 `<span>` elements to pin that nothing recurses. A regex pre-scan of the nesting depth was rejected: it cannot see the closes that HTML implies, so on sloppy pages it would truncate the document silently and lose Links.
- [Synchronous parsing cannot be cancelled by the watchdog] → `022` caps body sizes, the hostile fixtures pin deeply nested HTML, and `026`'s pool (v0.1) moves page preparation out of the event loop and ends a Page whose preparation takes over 30 seconds (`parse_timeout`, `026` D8).
- [User-supplied regexes applied to URLs controlled by the site (ReDoS)] → `022` caps URL length at 2,000 characters, and docs/crawling.md warns against nested quantifiers.
- [A fallback unit loses the URLs discovered from a URL whose unit failed] → It is counted in `record_failed`, and a continue re-queues the URL, which discovers them again.
- [Protego differs from Google's parser on edge cases] → The status mapping is ours and tested, and matching edge cases are pinned in pure-logic tests.
- [The Public Suffix List snapshot goes stale] → `publicsuffixlist` releases often, and the pin is updated with every release.
- [Windows delivers console control events to every process on the console] → CTRL_BREAK tests start the crawler in a new process group.
- [aiohttp's URL library quotes a URL given as text again: it decodes `%2F` in a query to `/` and encodes `[`, so the request would differ from `urls.url`] → The Fetcher builds `yarl.URL(url, encoded=True)` from the normalised URL (task 4.2), and a seam-3 test checks the request path against the recorded URL.
- [`parse_seed` and the link extractor take no `--strip-params` pattern yet (groups 1 and 3)] → The task that wires `--strip-params` into the Crawl (8.1 at the latest) passes it to both, so the Seed's `urls` row and every discovered target are stripped alike.
- [`urlsplit` strips only leading white space, so `http://site.test/a ` is recorded as `/a%20`, as aiohttp requests it] → The link extractor strips C0 controls and spaces around a reference and removes tabs and newlines inside it before resolving, as the URL Standard does (tasks 3.1 and 3.8); the Seed parser strips both ends.
- [One host in several spellings stays several URLs: IPv4 forms such as `127.1` and `0x7f.0.0.1`, and a trailing dot (`site.test.`), as aiohttp requests them; a host that only cannot resolve, such as `a..b.test`, is normalised and gets its DNS error when requested] → Group 2's `ScopeRules` decide whether such hosts are internal; the normaliser rejects only what cannot be requested.
- [Tests of group 1 named after no scenario, which the scenario count of task 15.1 ignores] → In `tests/crawl/test_urls.py`: the host table and the property against aiohttp's hosts (task 1.5), userinfo (1.12), the Seed scheme table and property (1.13), the never-raises properties of the Seed parser and of `--strip-params` patterns, and the brackets case (1.15).
- [`urljoin` follows RFC 3986, not the URL Standard that browsers follow] → Task 3.8 reads a reference as the URL Standard does before `urljoin` sees it (ruling of 2026-10-14), so the URL recorded is the URL a browser requests, as for hosts (D13). What stays: a `<source>` or `<track>` counts as video or audio only as a direct child of `<video>` or `<audio>`.
- [The link extractor costs about 4.3–5.3 ms per Page of 450 Links on an idle laptop, a third of it in `urljoin` (group 3's benchmark, `.git/writer-a-tools/bench_links.py`; a throttled machine measured about 6 times more)] → Three options wait for `026`'s benchmark (ruling of 2026-10-14): (a) a cheap test for `//` before the extra `urlsplit` of the empty-authority check; (b) no `urljoin` for an absolute reference already in the normaliser's normal form; (c) `gc=False` on `DiscoveredLink`, about 450 per Page. The cyclic garbage collector must stay on: the extractor leaves no cycles, and with it off the tail grew to hundreds of milliseconds.
- [Link types and elements that no scenario of this change drives (ruling of 2026-10-14)] → In `tests/crawl/test_links.py` (task 3.3): `test_each_element_gives_its_link_type`, one table over `<area>`, `next` and `prev`, `hreflang`, `mobile_alternate`, a feed as `misc`, `css`, `iframe` and `frame`, `javascript`, `media` from `<embed>` and `<object>`, `<video poster>` and a `<picture>` source's `srcset`; and `test_rel_tokens_are_lower_cased_and_nofollow_is_read_from_them`; from task 3.5, `test_links_are_read_from_the_decoded_document` and the hostile fixture `test_deeply_nested_html_gives_its_links`, from the review (task 3.7) `test_references_that_name_no_file_give_no_link`, from task 3.8 `test_references_resolve_as_browsers_resolve_them`, `test_queries_are_encoded_in_the_page_encoding` and, in `tests/crawl/test_decoding.py`, `test_each_encoding_of_the_standard_is_named_by_its_labels`, and in `tests/crawl/test_decoding.py` the decoding table `test_html_is_decoded_by_the_first_source_that_applies` and its never-raises property `test_decoding_any_bytes_gives_text`. `canonical`, `meta_refresh` and `amphtml` are built by the tasks that drive them (8.12, 7.7 and 7.8); until then a `<link rel="canonical">` or `rel="amphtml"` is a `misc` Link.
- [Tests of group 4 named after no scenario, which the scenario count of task 15.1 ignores] → In `tests/cli/test_crawl.py`: `test_a_seed_with_userinfo_is_rejected_with_a_hint_about_auth` (task 4.1); in `tests/crawl/test_spider_mode.py`: `test_the_request_is_for_the_recorded_url`, the seam-3 check of the request path against `urls.url` (task 4.2); in `tests/store/test_urls.py`: `test_the_units_of_urls_run_again_the_same`, which replays the units with `replay_now` (task 4.2); in `tests/test_code_style.py`: `test_only_the_store_imports_sqlalchemy` and its breach cases `test_an_import_of_sqlalchemy_outside_the_store_is_named` (design D14, task 4.2); in `tests/cli/test_crawl.py`: `test_the_result_has_the_fields_of_a_crawl` (task 4.6); in `tests/store/test_crawl_units.py`: `test_the_units_of_crawls_run_again_the_same` (task 4.6) and `test_the_state_is_checked_against_the_state_the_unit_reads` (task 4.8); in `tests/store/test_urls.py`: `test_the_frontier_read_uses_its_index`, which reads SQLite's plan of the frontier batch read: `urls_crawl_depth_id`, with no temporary B-tree for the order, so a later edit of the index or the query cannot turn a 500k-URL frontier read into a scan (design D1, ruling of 2026-10-14); in `tests/crawl/test_crawl_service.py` (task 4.12): `test_the_journal_mode_setting_reaches_the_crawl_file`, `test_a_secret_setting_is_redacted_in_the_recorded_config` and, on Windows only, `test_a_journal_warning_reaches_the_result`, which crawls into a Workspace reached through the machine's own administrative share (`//localhost/<drive>$/`), a real UNC path; in `tests/crawl/test_spider_mode.py` (review of group 4): `test_a_response_that_is_not_html_is_not_parsed`.
- [Tests of group 5 named after no scenario, which the scenario count of task 15.1 ignores] → In `tests/cli/test_crawl.py`: `test_an_invalid_exclude_pattern_is_rejected` (task 5.1); in `tests/crawl/test_hooks.py`: `test_handlers_get_the_outputs_of_the_extractors_that_did_not_fail` (task 5.5) `test_only_the_failing_handlers_rows_are_dropped` (task 5.7) and `test_a_unit_that_fails_with_the_file_is_never_completed` (task 5.13); in `tests/crawl/test_politeness.py`: `test_the_global_cap_is_four_times_the_concurrency_within_20_to_100` (task 5.15); in `tests/cli/test_crawl.py`: `test_a_concurrency_above_50_in_the_settings_file_is_refused` (task 5.16); from the review of group 5, in `tests/crawl/test_hooks.py`: `test_a_handler_that_fails_midway_keeps_none_of_its_rows`, `test_an_extractor_that_returns_no_struct_is_an_extractor_error`, `test_a_writer_that_ends_reports_why_it_ended` and `test_a_handler_gets_the_row_values_of_the_url`, in `tests/crawl/test_fetcher.py`: `test_a_host_that_dns_cannot_encode_is_a_dns_error`, and in `tests/test_network_guard.py`: `test_a_test_that_swallows_a_blocked_attempt_still_fails`, since the Fetcher now returns the guard's `NetworkAccessBlocked` as a URL's error instead of raising it.
- [Tests of group 6 named after no scenario, which the scenario count of task 15.1 ignores] → In `tests/crawl/test_crawl_service.py`: `test_the_dns_resolver_hook_reaches_the_crawl` (task 6.1); in `tests/crawl/test_external.py`: `test_each_url_records_whether_it_is_internal_and_in_scope` (task 6.2) and `test_each_url_points_to_its_origin`, with a port that makes another origin of one host (task 6.3); in `tests/cli/test_crawl.py`: `test_no_check_external_records_an_external_url_as_skipped`, the effect of the flag itself, since the scenario test sets the setting through the Crawl Service (task 6.4).
- [From task 5.13 a write failure sets the stop flag with `write_failed`, and the Crawl Service re-raises its error without writing `completed`, so the Command ends with `internal_error`, or `crawl_busy` (exit 5) as the writer raised it, and the Crawl stays `running`] → Task 12.9 declares `crawl_write_failed` (exit 7) and records the `failed` end through a fresh writer.
- [From task 5.1, a Seed that matches an `--exclude` pattern ends as a `completed` Crawl whose Seed is `skipped` as `excluded`] → Task 8.8 rejects it as `seed_out_of_scope` before any crawl file is created.
- [D10's warning log writes each warning once per code and host; group 5's warnings are counted ones, kept once per code, and no warning of it repeats per host yet] → The first task whose warning can repeat for each host (11.3's `possible_blocking`, 10.11's `robots_unreachable`) keys it by code and host.
- [Group 2's review applies the subfolder folder in `ScopeRules.decide`, pinned at seam 4, before tasks 8.4 and 8.5 drive it over HTTP] → Those tasks may pass on their first run; each then shows its red by a mutation of the folder check, as a guard does.
- [The ast guards of `tests/test_code_style.py` match names, so an aliased import (`from spider.crawl.urls import NormalizedUrl as N`) escapes design D13's guard, as `018` recorded for ADR-0006's] → Don't alias; the review checks it. The D13 guard also catches `cast(NormalizedUrl, ...)` with the type as a name or a string.
- [`docs/crawling.md` links the change's delta spec, `openspec/changes/020-add-crawl-core/specs/crawling/spec.md`, which the archive moves] → The archive commit points the link at `openspec/specs/crawling/spec.md`; `tests/test_docs_links.py` fails until it does.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds its tables and columns to the declared schema and to `docs/schema.md` in the same slice, and `schema_version` stays 1 (015 D5).

**Two pull requests** (ruling of 2026-10-14): `020` merges in two parts. PR #1 follows group 6, the thin slice, once CI is green on Windows, macOS and Linux (task 6.8): its code reaches main, the change stays open, and tasks.md is merged with only groups 1–6 ticked, so `030` and `040` can build on the slice. PR #2 follows groups 7–14 and the change check (group 15), with the archive.

## Interface points for later changes

- **`022`:** its timeout settings feed the watchdog function of D16, which keeps the watchdog at least 30 seconds longer than the Fetcher's total request deadline. It replaces the Fetcher implementation behind the Protocol of D8; uses the per-host gate of D7, `ScopeRules.is_internal`, the fake Fetcher and the DNS resolver hook; adds `urls` columns in its slices (`redirect_url_id` with its index `urls_redirect_url_id`), writes the `discovered_via`, `skip_reason`, `fetch_error` and `parse_error` values that this change already lists (D18), and adds its keys to `CrawlSettings`.
- **`024` (v0.2):** records a URL listed in a sitemap with `discovered_via` = `xml_sitemap` (a Link type, D5), never `sitemap`, and its sitemap files with `sitemap_input` or `sitemap_index`. All of these are already listed (D18), as is `sitemap_hreflang`.
- **`026`:** writes `parse_error` = `worker_crashed` and `parse_timeout`, already listed (D18), with `parsed` = 0, since nothing came out of the Page's preparation, the second when a Page's preparation passes its per-Page deadline and the worker is killed and replaced; benchmarks the engine as built; plugs its process pool into the executor seam of D9 without changing the engine or the extractors, and passes the settings snapshot to each worker once, as an argument each worker process starts with; it is never pickled with a response; uses the stop flag's grace period.
- **`030`:** stores every Link with this change's `LinkType` and `declared_in` (D5); adds its extractor, handler and pass to `default_hooks()`, with its row types and writers in `spider.store.pages` and `spider.store.links`; imports the robots directives parser, `DiscoveredLink` and the decoding function; its Page extractor takes the tree and `PageInput`, and its handler counts outlinks from `DiscoveredLink.is_internal` (D9); adds its keys to `CrawlSettings`, and `content_area` to page preparation's settings snapshot.
- **`040`:** adds its post-crawl pass, which materialises its Rules' Issues by their queries, in `spider.store.issues`. It registers no per-response handler, and reads `completed` or `stopped` as "the passes have run".
- **`060`:** adds `interrupted` to `TRANSITIONS`; uses `StopReason` for `crawl_runs.stop_reason` (D18); records the progress counters of D10 on its heartbeat for `status`; calls the continue operation for `resume`, with its kill-then-resume scenarios; sets the `StopSignal` from control rows (`requested`); builds the `CrawlContext` in the detached process; reuses validation and config resolution (D11); shows `paused_since` for a Crawl in a network pause (D16).

## Open Questions

These are deferrable: each would add a flag or column later without changing these specs.
- `--resolve host:port:address`, to crawl a pre-launch server under the production host name.
- Screaming Frog-style store/crawl switches per Link type, for example crawling `amphtml`.
- An opt-in cookie session, for sites that gate on a session cookie.
- Refusing External checks of private or link-local addresses, for example `169.254.169.254`, when crawling from cloud machines.
- A `robots_matched_line` column, Screaming Frog's "Matched Robots.txt Line", as a v0.2 candidate.
- Reading `<meta name="<token>">` for the robots user-agent token. `030` does not read crawler-specific meta elements in v0.1.
- A human-readable progress line when stderr is a terminal and `--format table` is used.
