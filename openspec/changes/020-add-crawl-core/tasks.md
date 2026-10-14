"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawling/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI, through `run_cli`; "seam 1, subprocess" is a real `spider` process through `run_cli_process`
- seam 2: services and the store API, with a real crawl store in `temp_workspace`
- seam 3: the real crawler and aiohttp against the local fixture site
- seam 4: pure logic, table-driven, with hypothesis where the task says so
- seam 3+6: crawl the fixture site, then read the documented tables read-only with `015`'s `query` and `crawl_row`
- "fake timing": seam 2 with the fake Fetcher and `FakeClock`, for timing scenarios only
- "fixture": a new fixture-site capability, test-first in `tests/fixture_site/`, without changing what an existing route kind does

"Done when" says what must be true, not which helper to write. Names appear only where another change depends on them (design, Interface points).

**No schema-first slices:** a table, column or index is added in the slice whose scenario first needs it, through `018`'s `public_table()` (an index as a named `Index` with `info["description"]`), with its description and its `docs/schema.md` row (in the table section's Columns or Indexes table) in the same commit, so the contract test (`015`'s, extended by `018`) is never red between commits. HTTP slices add the fixture pages they need.

**Dependencies:** a new runtime dependency (`aiohttp`, `protego`, `selectolax`, `msgspec`, `publicsuffixlist`) is added in the slice that first needs it, with its line in `tests/dependency_allowlist.txt`, and the startup allowlist test (`tests/cli/test_startup.py`) must still pass without allowing it.

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract.

**The robustness rule** (ROADMAP) applies to every task: a parser that a task adds gets its never-raises hypothesis property in that task or the one the group names, and a failure of one URL is recorded on that URL.

**The thin slice** (ROADMAP, Build order) needs groups 1–6: normalisation, the host Scope, hyperlink discovery, a foreground Crawl recorded through the writer, the hooks `030` and `040` plug into, `fetch_error` and `is_internal`. Groups 7–15 widen the change after that.

## 1. URL normalisation and Seeds (slice, seam 4)

- [x] 1.1 Drive "Scheme and host case, the default port and the fragment are normalised" and "A non-default port is kept", a trivial pair.

  Done when: the normaliser returns a `NormalizedUrl` (design D13), the only producer of that type, or its own rejection type, and never raises.
- [x] 1.2 Drive "Dot segments are resolved" and "An empty path becomes a slash", a trivial pair.
- [x] 1.3 Drive "Percent-encodings are normalised".
- [x] 1.4 Drive "Characters outside ASCII are percent-encoded".
- [x] 1.5 Drive "An internationalised host becomes ASCII".
- [x] 1.6 **Guard:** "The query and its parameter order are kept" and "A trailing slash is kept", a pair.
- [x] 1.7 **Guard:** "Normalising twice changes nothing", as a hypothesis property over generated http and https URLs.
- [x] 1.8 Drive "Normalising any text gives a URL or a rejection", as a hypothesis property over arbitrary text.
- [x] 1.9 Drive "Matching parameters are removed". Done when: `--strip-params` patterns apply as part of normalisation, keeping the order of the other parameters.
- [x] 1.10 Drive "Removing every parameter removes the query" and "Parameters are kept by default", a trivial pair.
- [x] 1.11 Drive "A bare host becomes an https Seed". Done when: the Seed parser returns a `NormalizedUrl` or a rejection that the Command reports as `invalid_url`.
- [x] 1.12 Fix: a URL with userinfo is an `InvalidUrl` ("userinfo"), never normalised (design D13), with a table case at seam 4.
- [x] 1.13 Fix: the Seed parser finds a scheme by design D13's rule (a scheme name and `:`, unless a port follows), so `mailto:`, `tel:`, `javascript:` and `ftp:` Seeds are rejected and `localhost:8080` gets `https://`, with table cases and a hypothesis property at seam 4: a Seed the parser accepts is http or https, and keeps the scheme its text names.
- [x] 1.14 Docs: write the "URLs" part of `docs/crawling.md` (the normalisation rules, the kept trailing slash, and `--strip-params`).
- [x] 1.15 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.
- [x] 1.16 **Guard:** design D13's rules, by an ast guard in `tests/test_code_style.py` over `src/spider`, with breach cases fed as source strings: `spider.crawl.urls` imports nothing of `spider`, at module level or inside a function, and `NormalizedUrl(` is called only in the modules of an explicit allowlist, which is `spider/crawl/urls.py` until group 4 adds the store's cast points.
- [x] 1.17 Perf: existing percent-encodings are normalised before new ones are written, so no escape is read twice, and each pass is skipped when its text gives it nothing to do; the idempotence property and the scenario tests guard it (design D13).
- [x] 1.18 Perf: a fast path returns a URL already in normal form unchanged, decided by one module-level regex. A hypothesis property over `st.from_regex` of that regex shows that the full normalisation returns every text it admits unchanged, and a second property over near misses (`%`, a dot segment, an upper-case host, a default port, a fragment, IPv4-looking hosts such as `127.01` and `0127.0.0.1`, `xn--` labels) shows that the fast and the full path agree (design D13).
- [x] 1.19 Perf: a bounded `functools.lru_cache` on the pure host encoder, as aiohttp's URL library has, with a comment saying why (design D13). ADR-0006's guard in `tests/test_code_style.py` refuses a memo without an explicit bound (`cache`, `lru_cache` bare, without `maxsize` or with `maxsize=None`), naming the module and function, with breach cases fed as source strings; the why comment stays a review item.

## 2. Scope decisions (slice, seam 4)

- [x] 2.1 Drive "The other scheme of the Seed host is internal" and "Another host is external by default", a trivial pair.

  Done when: `ScopeRules` (design D4) is a frozen value built from the Seed and the settings, whose decision on a `NormalizedUrl` is a pure function.
- [x] 2.2 Drive "The www host of an apex Seed is internal".

  Done when: registrable domains come from the bundled `publicsuffixlist`, and a table test of about 20 Seed/URL cases passes: apex and `www.` both ways, other subdomains, ports, IDN hosts, public suffixes such as `co.uk`, IP addresses, single-label hosts and upper case.
- [x] 2.3 **Guard:** "The apex of a www Seed is external".
- [x] 2.4 Drive "Subdomains are internal with the subdomains Scope".
- [x] 2.5 **Guard:** "A public suffix is not treated as the site".
- [x] 2.6 Drive "The folder of a Seed page is its parent folder".
- [x] 2.7 Drive "Exclude wins over include".
- [x] 2.8 Docs: write the "Scope" part of `docs/crawling.md` (host rules, the apex-to-www rule and why it goes one way, `--scope`, subfolder folders, include and exclude, and a warning about slow regexes).
- [x] 2.9 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. The link extractor (slice, seam 4)

- [x] 3.1 Drive "A relative link is resolved against the base href".

  Done when:
  - the link extractor takes HTML bytes, their Content-Type, the response URL and an `is_internal` function, parses once with `selectolax.lexbor.LexborHTMLParser`, and returns `DiscoveredLink` values (design D5), which `030` enriches.
  - `DiscoveredLink` is a `msgspec.Struct` with `frozen=True` and `kw_only=True` (ADR-0006), and `msgspec` comes in with this slice.
  - `018`'s ADR-0006 guard in `tests/test_code_style.py` also refuses a class whose base is `Struct` or `msgspec.Struct` without `frozen=True` among its class keywords, naming the module and the class. A breach case feeds it a source string with such a class and sees it red, and the guard passes on the code.
- [x] 3.2 Drive "Every srcset candidate is an image Link" and "Video and audio sources are video and audio Links", a pair.
- [x] 3.3 Drive "rel previous is a pagination Link" and "A link element of another rel is a misc Link", a pair.
- [x] 3.4 Drive "References that are not http or https are ignored" and "A malformed reference is ignored", a trivial pair.
- [x] 3.5 Drive "The link extractor accepts any bytes", as a hypothesis property over arbitrary bytes, Content-Types and malformed HTML.

  Done when: decoding follows design D5's order with replacement characters, in one function that `030` imports.
- [x] 3.6 Docs: add the Link type table, with the types listed for later releases, and decoding to `docs/crawling.md`.
- [x] 3.7 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.
- [x] 3.8 Fix: references resolve as the URL Standard resolves them in a browser (ruling of 2026-10-14), at seam 4, by table tests, with the never-raises property of task 3.5 extended to backslashes, slashes and non-UTF-8 Content-Types.

  Done when:
  - in an http or https URL, a `\` before the query or fragment is read as `/`, so `href="\catalog"` is `/catalog`, not a false broken `/%5Ccatalog`
  - after the scheme, or at the start of a relative reference, any run of `/` and `\` introduces the host, as browsers read `///x` and `http:\\x`; an empty host (`//`, `https:` on an http Page) gives no Link
  - leading and trailing C0 controls and spaces are stripped, and tabs and newlines inside the value are removed
  - on a Page decoded as neither UTF-8 nor UTF-16, the query of a resolved reference is percent-encoded in the Page's encoding, and a character that encoding cannot hold becomes `&#NNNN;` with its `#` encoded, as the URL Standard says; the path stays UTF-8
  - design Risks drops the urljoin deferrals that this task resolves and lists its non-scenario tests, and a non-scenario test pins labels of every encoding of the decoding table

## 4. Walking skeleton: a foreground Spider crawl (slice)

- [x] 4.1 Drive "An invalid Seed is rejected" at seam 1.

  Done when: `spider crawl <url>` is registered with `@command_meta(name=CRAWL, output="document", events=True)`, its adapter calls the Crawl Service, `invalid_url` is declared in `spider.output.codes`, and the Workspace holds no new crawl file. A Seed rejected for its userinfo gets a hint that names `022`'s `--auth` (design D13).
- [x] 4.2 Drive "The Seed is fetched and recorded" at seam 3+6.

  Done when:
  - the Crawl Service's start operation creates the Crawl with `015`'s `create_crawl`, and builds the `CrawlContext` (design D15) in one place, opening and closing `CrawlWriter` through `asyncio.to_thread`, and submits each URL's unit with `017`'s `submit_async()`, so the URL's task ends at the submit (design D2)
  - every `NewCrawl` gets both of its required fields, `secret_names` and `journal_setting`, from this first slice on; task 4.12 checks what they do
  - the `Fetcher` Protocol (design D8) has a one-hop aiohttp implementation
  - the first `urls` columns (`id`, `url`, `host`, `crawl_depth`, `discovered_via`, `fetch_state`, `status_code`) and the unique index `urls_url` are declared with `018`'s `public_table(..., change=20)`, each enumeration with every value of design D18, with their `docs/schema.md` rows; `018`'s guard over index names switches on its assertion that it saw an index
  - every writer unit is defined in a `spider.store.*` module, follows `017` D7 (deterministic given the file's state, values as results), and its seam-2 test forces a replay with `017`'s `replay_now(writer)` from `tests/support/writer.py` (design D14); a guard in `tests/test_code_style.py` fails, naming the module, when a module of `src/spider` outside `spider/store/` and `spider/services/schema.py` imports `sqlalchemy`, at module level or inside a function, with cases that feed it source strings to show it is sharp (design D14)
- [x] 4.3 **Guard:** "The Seed is kept as given in seeds" (seam 3+6) and "The ways a URL is found are an enumeration" (seam 1), a pair. `015`'s `create_crawl` writes the Seeds as given, and task 4.2 declared `discovered_via` from the `LinkType` `Literal` (design D5).
- [x] 4.4 Drive "Pages linked from the Seed are crawled" at seam 3+6, and "Indexes of urls" at seam 1, a pair.

  Done when:
  - the scheduler takes queued URLs depth by depth in `urls.id` order through a writer unit that only reads, run with `run_async()` and committing nothing, above a per-depth cursor of the run, over the partial index `urls_crawl_depth_id`, declared with its description (design D1)
  - hyperlinks are discovered by the page preparation function, called through the in-process executor of the `CrawlContext`, and each `DiscoveredLink` carries `is_internal` from the `ScopeRules` in its settings snapshot (design D5, D9)
  - page preparation decodes and parses once: the link extractor gains a tree-level entry, `links_in_tree(tree, base=, encoding=, is_internal=)`, with `base_url(tree, url, encoding)` for the base, that page preparation calls with the tree the registered extractors get too, and `extract_links` stays as its wrapper over bytes (design D9)
  - new URLs are deduplicated by `urls_url` inside the URL's unit, with no in-memory map of URLs (design D1)
- [x] 4.5 Drive "A discovered URL points to where it was found" at seam 3+6.

  Done when: `found_on_url_id` is declared with a foreign key to `urls.id`, the first in the schema, and `docs/schema.md` shows it as `018` documents references; `018`'s guard over reference columns switches on its assertion that it saw a reference.
- [x] 4.6 Drive "The result counts a small site" and "A completed Crawl exits with code 0" at seam 1, a trivial pair.

  Done when: the result's counts come from queries over `urls`, never from counters, and the `parsed` column exists.
- [x] 4.7 **Guard:** "The crawl Command prints one document", at seam 1.
- [x] 4.8 Drive "Only the listed transitions are allowed" and "An early end needs a reason of its kind" at seam 4, a trivial pair; the first as a check over every pair of states.

  Done when: `TRANSITIONS` and `check_transition` exist (design D12), `StopReason` is a `Literal` next to `CrawlState`, and `015`'s `set_state` takes the `stop_reason` and checks the transition against the state it reads in the same unit.
- [x] 4.9 Drive "A completed Crawl records its state" at seam 3+6. Done when: `crawl.stop_reason` is declared, with its values from `StopReason` and its `docs/schema.md` row.
- [x] 4.10 Drive "The first event line is the start event" at seam 1.
- [x] 4.11 Drive "The recorded config holds every registered crawl setting" at seam 1, since the scenario reads `spider commands`.

  Done when: `[crawl]` is registered in `build_app` as `"spider.crawl.settings:CrawlSettings"` and passes `010`'s table-rules test, every crawl option declares its setting with `OptionMeta(setting=...)`, and `NewCrawl.config` holds every registered table. Its one option is `--concurrency`, which task 4.13 needs: an option is declared by the task that applies it, so none is inert (ruling of 2026-10-14), and `--max-depth`, `--max-urls` and `--rate` come with tasks 9.5, 9.7 and 11.1.
- [x] 4.12 Wire `015`'s journal mode (group 8) and redaction (group 9), at seam 2.

  Done when: the `crawl` adapter always passes `spider.cli.options.secret_names(<its Click command>, <the settings tables>)` to the Crawl Service, which puts it in `NewCrawl.secret_names` (`create_crawl` redacts by itself); and the Crawl Service always sets `NewCrawl.journal_setting` from the resolved `[store] journal_mode`, `"auto"` included, since neither field has a default, so `[store] journal_mode = "delete"` gives `crawl.journal_mode` = `delete`, and a `store_wal_unavailable` warning that `create_crawl` reports reaches the result's `warnings` (and `crawl.warnings` once task 12.3 declares it).
- [x] 4.13 Drive "spider.toml sets a crawl setting" and "A flag overrides spider.toml" at seam 1, a trivial pair.
- [x] 4.14 Drive "Response timing is recorded" at seam 3+6.
- [x] 4.15 Drive "The Content-Type is recorded as received" at seam 3+6.
- [x] 4.16 Docs: write the `spider crawl` reference in `docs/crawling.md` (the result fields, the event table, exit codes, `[crawl]` keys), and the `urls` and `crawl` columns and indexes so far in `docs/schema.md`.
- [x] 4.17 Review: run the code-review skill on group 4's commits, also against `017`'s unit contract (D7) and prebuilt statements (D9), ADR-0005's naming rules and ADR-0006 (slots on per-URL and per-Link records, `kw_only` above three fields), then refactor with the whole suite green.

## 5. Hooks, and one URL never stops the Crawl (slice)

- [x] 5.1 Drive "An excluded URL is never requested" (seam 3) and "An excluded URL is recorded as skipped" (seam 3+6), a trivial pair.

  Done when:
  - `--exclude` is declared, repeatable, with `OptionMeta(setting="crawl.exclude")` and the default `[]`, so it is not inert (ruling of 2026-10-14)
  - its patterns are compiled before any crawl file is created, and an invalid one is `invalid_pattern` (exit 2, the pattern in `details`), declared here, with a non-scenario test at seam 1; task 8.7 adds `--include`'s
  - `skip_reason` is declared, and an excluded URL is decided when it is dispatched and recorded in its own unit without a request, so it is decided once; a skipped URL never holds up the depth barrier (design D3) and is never counted as a request
- [x] 5.2 **Guard:** "A skipped URL has no response data", at seam 3+6.
- [x] 5.3 Drive "A registered handler sees every URL once" at seam 2.

  Done when: `Hooks` and `default_hooks()` exist (design D9), the Crawl Service takes the `Hooks` to use, a handler is pure and returns store rows, and the store writes them in the unit that records the URL's final state (design D14).
- [x] 5.4 Drive "Post-crawl passes run before a Crawl is completed" at seam 2. Done when: a pass is a store function that submits its own units, and runs before `completed` is written.
- [x] 5.5 Drive "An extractor error is recorded", "The Crawl continues after an extractor error" and "Links of a Page whose extractor failed are followed" at seam 3+6. Done when: `parse_error` and `parse_error_message` are declared, the `parsed` column says that it means parsed with its Links found, and a registered extractor's failure is recorded as `extractor_error`, with `<name>: <type>` as its message, while the URL keeps `parsed` = 1, its Links are followed and handlers get the other extractors' outputs (ruling of 2026-10-14). An extractor is a module-level function of the parsed tree and a frozen `PageInput` (design D9).
- [x] 5.6 Drive "Parse failures are counted in one warning" at seam 2, through the result's `to_json()`, which the CLI prints as it is: only the Crawl Service takes the test's extractor (review of group 5).

  Done when: the Crawl Service's warning log (design D10) keeps one entry per counted warning with `details.count` and `details.first_url`, writes it to stderr when it first occurs, and `parse_failed` is declared.
- [x] 5.7 Drive "A failing handler does not stop the Crawl" at seam 2. Done when: `handler_failed` is declared, and only the failing handler's rows are dropped.
- [x] 5.8 Drive "Deeply nested HTML does not stop the Crawl" at seam 3+6, a hostile fixture page of 10,000 nested `<div>` elements, which lexbor parses in about 50 ms (design Risks).
- [x] 5.9 **Guard:** "Undecodable bytes do not stop the Crawl", at seam 3+6, a hostile fixture page. Decoding with replacement comes from task 3.5.
- [x] 5.10 Drive "A closed port is a refused connection" at seam 3+6. Done when: `fetch_error` and `fetch_error_message` are declared, and the Fetcher returns every request failure in its result, never as an exception (design D8).
- [x] 5.11 Fixture: a route option that resets the connection after part of the body, test-first.
- [x] 5.12 Drive "A connection reset in the body is a connection error" at seam 3+6.
- [x] 5.13 Drive "A URL whose rows cannot be written is recorded as an error" at seam 2.

  Done when:
  - a failed unit gets a fallback unit that records only the URL's state (`fetch_state` = `error`, `fetch_error` = `record_failed`, the error in `fetch_error_message`), and `record_failed` is declared as a value and as a counted warning
  - only design D2's allowlist (after unwrapping `DBAPIError.orig`: `sqlite3.IntegrityError`, `DataError`, `InterfaceError`, and non-database exceptions of our row code, checked after the writer's own errors `CrawlWriterClosedError`, `CrawlWriterReplayError` and the `SpiderError` `crawl_busy`, which are never one row's) leads to `record_failed`; every other `sqlite3.DatabaseError`, a unit that fails or differs in `017`'s replay, a failing fallback, a failed commit or `CrawlWriterClosedError` sets the stop flag with `write_failed` instead
  - no Future that `submit_async` returns is dropped: each one's outcome reaches the engine through its callback (design D2), so a Crawl is never `completed` with a URL whose unit failed, and no "Future exception was never retrieved" reaches stderr (review of group 4)
- [x] 5.14 Fixture: a count of the most simultaneous requests, test-first.
- [x] 5.15 Drive "At most five requests to a host by default" and "A lower concurrency is honoured" at seam 3, a trivial pair.

  Done when: the URLs of a frontier batch are crawled by concurrent tasks, bounded by a semaphore per host and the global cap of design D7 (4 × concurrency, clamped to 20–100), and the next Crawl Depth's first frontier read waits until every task of the open depth has submitted its unit or ended (design D3); task 9.3 adds that checks never wait. Tasks 5.14–5.16 were 11.1–11.3: concurrent tasks change the engine's loop, so they come before PR #1, and groups 7–14 never build on a sequential one (ruling of 2026-10-14).
- [x] 5.16 Drive "A concurrency of zero is rejected" at seam 1.
- [x] 5.17 Docs: document the Fetcher Protocol, `Hooks` and how `030` and `040` add extractors, handlers, store rows and passes, in `docs/architecture.md`; and the per-URL failure outcomes and the per-host and global request limits in `docs/crawling.md`.
- [x] 5.18 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Internal and External URLs over HTTP (slice)

- [x] 6.1 Fixture: a second fixture site instance and the DNS resolver hook, which maps `site.test` and `www.site.test` to the first instance and `other.test` to the second, and fails every other name, test-first. Done when: the hook goes into the Crawl through the context builder (design D15).
- [x] 6.2 Drive "An External URL is checked" at seam 3+6. Done when: `is_internal` and `in_scope` are declared.
- [x] 6.3 Drive "An External origin gets its own row" at seam 3+6. Done when: the `origins` table is declared with `public_table(..., change=20)`: `id`, `origin` (with the named unique index `origins_origin`, never `unique=True`), `host` and `is_internal`, with its `docs/schema.md` section; `urls.origin_id` is declared NOT NULL with a foreign key to `origins.id`; and the unit that records a URL records its origin (design D18).
- [x] 6.4 Drive "External checks can be turned off" at seam 3.
- [x] 6.5 Drive "An unknown host is a DNS error" at seam 3+6.
- [x] 6.6 Docs: document External URL checks and the `fetch_error` codes in `docs/crawling.md`.
- [x] 6.7 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.
- [ ] 6.8 PR #1 (design, Migration Plan): verify that the whole suite passes in CI on Windows, macOS and Linux with the coverage gate on the branch, then hand over to the manager, who pushes and opens PR #1. The change stays open, with groups 7–16 unticked. No option of `spider crawl` is inert at PR #1: each declared option has a test of its effect.

## 7. Robots directives and Link following (widening)

- [x] 7.1 Drive "Meta robots directives are read case-insensitively" at seam 4. Done when: the robots directives parser is a pure function that `030` imports, whose fields carry `030`'s column names (design D6).
- [x] 7.2 Drive "A header for another crawler does not apply" at seam 4.
- [x] 7.3 Drive "A header for the robots user-agent token applies" at seam 4.
- [x] 7.4 Drive "none means noindex and nofollow" at seam 4.
- [x] 7.5 Drive "A directive with a value is not a user-agent prefix" at seam 4.
- [x] 7.6 **Guard:** "The robots directives parser accepts any values", as a hypothesis property at seam 4.
- [x] 7.7 Drive "A meta refresh target is followed" at seam 3.
- [x] 7.8 Drive "amphtml targets are not requested" at seam 3+6.
- [x] 7.9 Drive "A canonical in an HTTP header is followed" and "An HTTP Refresh target is followed" at seam 3, a pair. Done when: the HTTP `Link` and `Refresh` headers of in-Scope 2xx responses are read, parsed or not.
- [x] 7.10 Drive "Links on an error page are not followed" at seam 3+6. Done when: only in-Scope 2xx HTML responses are parsed. The 2xx and HTML checks exist since group 4's review, so this may pass on its first run; then it shows its red by a mutation, as a guard does.
- [x] 7.11 Drive "A nofollow link is not requested" at seam 3+6.
- [x] 7.12 Drive "A page-level nofollow applies to every hyperlink" at seam 3+6.
- [x] 7.13 Drive "A nofollow target reached through a followed Link is fetched" at seam 3+6. Done when: the re-queue takes the followed Link's `crawl_depth`, `discovered_via` and `found_on_url_id` (design D5), the replay test of `spider.store.urls` covers a re-queue, and the descriptions of `discovered_via` and `found_on_url_id` in `docs/schema.md` say so.
- [x] 7.14 Drive "Nofollow Links are followed on request" at seam 3+6.
- [x] 7.15 Perf: record each URL that a Page links to once. A Page of about 390 hyperlinks names about 310 distinct URLs, and the executemany of their `INSERT … ON CONFLICT` rows is about 80% of its unit in 026's direct-mode benchmark (about 24 URLs/s). The engine collapses a Page's Links to one row per URL after the follow decision: the URL is followed when any of its occurrences is, and its `discovered_via` is that of its first followed occurrence in document order, or of its first occurrence when none is followed (design D5), so 7.11–7.13 never let a nofollow Link hide a followed one. Done when: a test at seam 4 on the discovered-URL function pins it, and the commit gives the numbers before and after.
- [x] 7.16 Perf: an enumeration's CHECK lists its values as equalities joined by OR. SQLite compiles an `IN` list of more than two values into an ephemeral index, which an executemany builds again for every row: five for each `urls` row, about 118 µs per row through SQLAlchemy, and slower after about 70,000 rows (026's diagnosis of 2026-10-14). Done when: a guard refuses an `IN` list of more than two values in the CHECKs of a new crawl file, `public_table` writes the OR chain (a flag keeps `IN (0, 1)`), ADR-0005's consequences state the rule, and the commit gives the µs per row before and after.
- [x] 7.17 Seam: the page executor's lifecycle and its backlog, for `026`'s parse pool (design D7, D9, D15; the rulings). `PageExecutor` gains `async start(settings)`, `async close()` and `backlog`; the engine calls `start` once, with the final Scope, right after the Seed is recorded (`022` moves that one call to the end of the Seed's Redirect Chain); `default_page_executor()` in `spider.services.hooks` selects the in-process executor, `start_crawl` takes `pages=` as it takes `resolver=`, and `_crawl_context` closes the executor, also when the Crawl fails. `RequestLimits` holds the global request cap around each request, after the host's slot, and bounds the URL tasks in flight by the cap plus the executor's backlog. Done when: a fake executor passed as `pages=` gets `start` once, before the Seed's preparation, and `close` at the end, also when the Crawl fails; the two caps are table-tested at seam 4; the concurrency scenarios stay green.
- [x] 7.18 Fix: a certificate failure is `tls_error`, not `connection_error`. aiohttp's `ClientConnectorCertificateError` is both a `ClientSSLError` and a `ClientConnectorError`, and the Fetcher's mapping met only the second, so an Internal HTTPS site with a bad certificate would count toward the network pause (D16) and end `site_unreachable`, the case its `tls_error` exclusion was ruled for. Done when: a `ClientSSLError` branch comes first, and a seam-4 table maps every aiohttp error the Fetcher can meet to its `fetch_error`, so a subclass caught by an earlier branch fails a test (`022` task 6.2 extends the table).
- [x] 7.19 Drive "A robots meta inside noscript does not apply" at seam 4. lexbor parses with scripting off, so a `<meta>` inside `<noscript>` is an element of its tree; browsers and Google's renderer parse with scripting on, where the content of `<noscript>` is text. Head metadata inside `<noscript>` is ignored: a robots meta, a meta refresh and a `<link>` give nothing. Done when: a test pins the user's decision that the Links of a body `<noscript>` are discovered and followed (design D5).
- [ ] 7.20 Seam: the page executor's `workers`, reported by `crawl_started` as `parse_workers`, for `026`'s pool (design D9; the rulings). `workers` is the number of processes that prepare Pages besides the crawl process: 0 for the in-process executor. `start_crawl` builds the executor before it reports `crawl_started` (nothing spawns before `start`), and hands it to the context builder, which closes it. Done when: `crawl_started` carries `parse_workers` 0 with the in-process executor, and a fake executor's count when one is passed as `pages=`; `docs/crawling.md` lists the field.
- [x] 7.21 Docs: add the robots directives rules, nofollow handling and which responses are parsed to `docs/crawling.md`.
- [ ] 7.22 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Scope over HTTP and Section Crawls (widening)

- [ ] 8.1 Drive "URLs that differ only in stripped parameters are fetched once" at seam 3.
- [ ] 8.2 Drive "The subdomains shorthand conflicts with a subfolder Scope" at seam 1. Done when: `option_conflict` is declared.
- [ ] 8.3 Drive "A Seed without its trailing slash is rejected" at seam 1. Done when: `subfolder_is_root` is declared, with a hint built from the Seed.
- [ ] 8.4 Drive "Pages inside the folder are followed" at seam 3+6.
- [ ] 8.5 Drive "Pages outside the folder are checked but not followed" at seam 3+6.
- [ ] 8.6 Drive "A URL that matches no include pattern is checked but not followed" at seam 3+6.
- [ ] 8.7 Drive "An invalid pattern is rejected" at seam 1. Done when: an invalid `--include` pattern is `invalid_pattern`, which task 5.1 declared for `--exclude`, before any crawl file is created.
- [ ] 8.8 Drive "A Seed outside the Scope is rejected" at seam 1. Done when: `seed_out_of_scope` is declared.
- [ ] 8.9 Drive "A subfolder Crawl is a Section Crawl" at seam 1.
- [ ] 8.10 Drive "An include pattern makes a Section Crawl" and "Exclude patterns alone do not make a Section Crawl" at seam 3+6, a trivial pair.
- [ ] 8.11 Drive "A subfolder Scope is recorded" at seam 3+6. Done when: `crawl.scope` is declared NOT NULL, with the Seed hosts in order, and `create_crawl` writes it with the `crawl` row from a `scope` field added to `NewCrawl` (design D18).
- [ ] 8.12 Drive "A www Seed whose canonical names the apex is reported" at seam 1. Done when: `seed_base_mismatch` is declared, and the Scope is unchanged.
- [ ] 8.13 **Guard:** "A www Seed whose Links stay on www is not reported", at seam 1.
- [ ] 8.14 Docs: document Section Crawls, the recorded Scope and `seed_base_mismatch` in `docs/crawling.md`.
- [ ] 8.15 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Resources, Crawl Depth, limits and invariants (widening)

- [ ] 9.1 Drive "An image is checked but not parsed" at seam 3+6. Group 4's review parses only HTML, so the parse half may pass at once; its red then comes from a mutation.
- [ ] 9.2 **Guard:** "A broken image is recorded", at seam 3+6.
- [ ] 9.3 Drive "The shortest path wins over a faster, longer one" at seam 3+6. Done when: followed URLs of depth d+1 wait for every followed URL of depth d, and checks never wait (design D3).
- [ ] 9.4 Drive "A Resource is one deeper than its Page" at seam 3+6.
- [ ] 9.5 Drive "Links beyond the limit are not requested" at seam 3+6. Done when: `--max-depth` is declared with `OptionMeta(setting="crawl.max_depth")` and the default `None`, no limit (design D11).
- [ ] 9.6 Drive "Resources are checked beyond the depth limit" at seam 3+6.
- [ ] 9.7 Drive "The Crawl stops at the limit" at seam 1. Done when: `--max-urls` is declared with `OptionMeta(setting="crawl.max_urls")` and the default `None`, no limit, and the `stopped` end goes through `check_transition` with `max_urls`.
- [ ] 9.8 Drive "URLs not requested stay queued" at seam 3+6.
- [ ] 9.9 Drive "The limit warning says how to continue" at seam 1. Done when: `max_urls_reached` is declared, with a hint built from `spider.naming`.
- [ ] 9.10 Drive "The limit holds under concurrency" at seam 3. Done when: requests in flight count toward the limit.
- [ ] 9.11 **Guard:** "There is no limit by default" (seam 1) and "No limit is recorded as null" (seam 3+6), a pair.
- [ ] 9.12 Drive "A limit below one is rejected" at seam 1.
- [ ] 9.13 **Guard:** "Each URL is requested once", at seam 3.
- [ ] 9.14 **Guard:** "A link cycle ends", at seam 3+6.
- [ ] 9.15 **Guard:** "Followed URLs start in discovery order", at seam 3.
- [ ] 9.16 Drive "Post-crawl passes run when the URL limit stops a Crawl" at seam 2.
- [ ] 9.17 Docs: document Resources, Crawl Depth, `--max-depth`, `--max-urls` (no default, what counts) and the dispatch order in `docs/crawling.md`.
- [ ] 9.18 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. robots.txt (widening)

- [ ] 10.1 Drive "The group for the tool's token applies" at seam 4. Done when: the robots.txt reader is on Protego and reads at most 512,000 bytes, decoded with replacement.
- [ ] 10.2 Drive "Another token can be chosen" at seam 4.
- [ ] 10.3 **Guard:** "Any robots.txt gives a decision", as a hypothesis property at seam 4.
- [ ] 10.4 Drive "robots.txt is fetched once per origin" at seam 3.
- [ ] 10.5 Drive "A disallowed URL is not requested" (seam 3) and "A disallowed URL is recorded as blocked" (seam 3+6), a trivial pair. Done when: `blocked_by_robots_txt` is declared.
- [ ] 10.6 Drive "robots.txt is stored with its origin" and "A URL that is not requested still points to its origin" at seam 3+6, a pair. Done when: the `robots_*` columns of `origins` are declared, with `robots_state` and `robots_sitemaps` NULL until robots.txt is fetched.
- [ ] 10.7 Drive "A blocked Seed is reported" at seam 1. Done when: `seed_blocked_by_robots_txt` is declared.
- [ ] 10.8 Drive "Disallowed URLs are crawled and still labelled" at seam 3+6.
- [ ] 10.9 Drive "A missing robots.txt allows everything" at seam 3+6.
- [ ] 10.10 Drive "An unreachable robots.txt blocks its origin" at seam 3+6.
- [ ] 10.11 Drive "An unreachable robots.txt of the site is reported" at seam 1. Done when: `robots_unreachable` is declared.
- [ ] 10.12 Drive "A redirected robots.txt is followed" at seam 3+6.
- [ ] 10.13 Drive "More than five robots.txt redirects count as missing" at seam 3+6.
- [ ] 10.14 Drive "A dead External domain is a DNS error" at seam 3+6, with the DNS resolver hook of task 6.1.

  Done when: each URL of an origin whose robots.txt request got no HTTP response is recorded with `fetch_state` = `error` and that request's `fetch_error`, without a request of its own, with a `fetch_error_message` that names the robots.txt request; the origin has `robots_state` = `unreachable`, `robots_status_code` NULL, and the request's error in `robots_fetch_error` and `robots_fetch_error_message`, declared with their `docs/schema.md` rows and the CHECK values of the `fetch_error` `Literal`; 5xx and 429 stay `robots_unreachable`; and "An unknown host is a DNS error" still passes (design D6). The Seed's origin pauses the Crawl instead from task 12.6 on.
- [ ] 10.15 Docs: document robots.txt handling (status mapping, no HTTP response, `--ignore-robots`, `--robots-user-agent`, Crawl-delay) in `docs/crawling.md`.
- [ ] 10.16 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Politeness (widening)

- [ ] 11.1 Drive "Requests to a host are spaced by the rate", fake timing.

  Done when: `--rate` is declared with `OptionMeta(setting="crawl.rate")` and the default `None`, no limit; the fake Fetcher exists in `tests/support/` and goes into the Crawl through the context builder with `FakeClock`; and every wait of the engine goes through the context's `Clock`.
- [ ] 11.2 **Guard:** "Crawl-delay is not applied", fake timing.
- [ ] 11.3 Drive "Many 403 responses raise one warning" at seam 1. Done when: `possible_blocking` is declared.
- [ ] 11.4 Docs: document politeness defaults in `docs/crawling.md`.
- [ ] 11.5 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Events, failures and backstops (widening)

- [ ] 12.1 Drive "Every stderr line is an event or a diagnostic" at seam 1.
- [ ] 12.2 **Guard:** "A warning is written as a diagnostic", at seam 1.
- [ ] 12.3 Drive "Warnings are stored as diagnostics" at seam 3+6. Done when: `crawl.warnings` is declared NOT NULL, `[]` when the Crawl is created, and holds every warning of the result, `store_wal_unavailable` included.
- [ ] 12.4 Drive "Progress events come every 10 seconds", fake timing. Done when: the `urls` counts of `progress` come from counters that the outcomes of committed units update, seeded once by a counting query when the run starts, and no count over `urls` runs for each event (design D10).
- [ ] 12.5 Drive "Events are UTF-8 on Windows (Windows)" at seam 1, subprocess, Windows in CI.
- [ ] 12.6 Drive "An unreachable Seed fails the Crawl" at seam 1.

  Done when: `--network-wait` is declared with `OptionMeta(setting="crawl.network_wait")`, default 1800, in `CrawlSettings`; until the Seed's origin has given an HTTP response, its robots.txt or Seed request without one pauses the Crawl at once, and with `--network-wait 0` no probe starts; the `failed` end goes through `check_transition` with `seed_unreachable`; and the adapter returns the result as an `Outcome` (design D16).
- [ ] 12.7 Drive "An unreachable Seed is reported by one error" at seam 1. Done when: `seed_unreachable` is declared, with a hint about network access and sandboxed agents that says how long the Crawl waited.
- [ ] 12.8 Drive "Post-crawl passes do not run for a failed Crawl" at seam 2.
- [ ] 12.9 Drive "A write failure fails the Crawl" at seam 1, with SQLite's `max_page_count` set by a test-scoped connection listener so that SQLite reports a full disk.

  Done when: `crawl_write_failed` is declared, the stop flag ends the Crawl with `write_failed`, the service records the end once through a fresh writer, and a writer's `crawl_busy` is reported as it is (exit 5). The full disk shows inside a unit as an `sqlite3.OperationalError`, which is not in design D2's allowlist, so it is `write_failed`, never `record_failed`.
- [ ] 12.10 Drive "Recording that fails for every URL fails the Crawl" at seam 1, with a handler and a row writer registered for the test. It comes after 12.9, which declares `crawl_write_failed`, and builds on task 5.13's fallback unit.

  Done when: the record-failure count of design D16 trips at `RECORD_FAILURE_LIMIT` (100) URL units in a row that failed on their first run, a URL unit that commits resets it, fallback units do not count, and the constant's comment says why.
- [ ] 12.11 Drive "A network wait of zero fails at once" at seam 1, with the reset route of task 5.11.

  Done when: the network pause's count of design D16 trips at `max(8, 2 × concurrency)` Internal requests in a row without an HTTP response, counting the codes D16 lists and the URLs recorded from an Internal origin's robots.txt without a response, but never `tls_error` or an External request; any response resets it; and with `--network-wait 0` the pause ends at once with `site_unreachable`.
- [ ] 12.12 Drive "Losing the site is reported by one error" at seam 1. Done when: `site_unreachable` is declared, with a hint that says how long the Crawl waited and names `spider resume` through `spider.naming`.
- [ ] 12.13 **Guard:** "Dead External links do not fail the Crawl", at seam 1.
- [ ] 12.14 Drive "A stuck request is ended by the watchdog", fake timing.

  Done when: `watchdog` is a `fetch_error` value; the watchdog waits on the context's `Clock` for a time computed from the settings by one pure function, `max(120 s, the Fetcher's total request deadline + 30 s)`, tested at seam 4; and a request it ends counts as one without an HTTP response for the network pause.
- [ ] 12.15 Drive "Probes back off to once a minute" at seam 4. Done when: one pure function gives the probe times of a network wait: 5, 10, 20 and 40 seconds after the pause began, then every 60 seconds, none later than the wait.
- [ ] 12.16 Drive "A dead section does not stop the Crawl", fake timing.

  Done when: probes request the Seed URL through the per-host gate on the context's `Clock`, are not recorded and do not count toward `--max-urls`; the first answering probe resumes the Crawl with the errors kept; and `network_paused` is declared and counted, with `details.count` and `details.total_seconds`.
- [ ] 12.17 Drive "An outage pauses and resumes the Crawl", fake timing.

  Done when: the `crawl_paused` and `crawl_resumed` events carry the data of the spec's event table; no request starts while paused; and a request that ends without an HTTP response while paused is not recorded, so its URL stays `queued` and is requested again when the Crawl resumes.
- [ ] 12.18 Drive "URLs that failed in an outage are requested again", fake timing. Done when: a later answering probe re-queues the URLs of the count, each at most once in a run, and the engine dispatches them ahead of the frontier read.
- [ ] 12.19 Drive "A Crawl that waits longer than the network wait fails", fake timing.
- [ ] 12.20 Drive "Progress events say when the Crawl is paused", fake timing. Done when: `progress` carries `paused`, and its events go on during a pause.
- [ ] 12.21 Drive "A negative network wait is rejected" at seam 1.
- [ ] 12.22 Drive "A Seed that answers late is crawled", fake timing. Done when: a probe that answers before any response from the Seed's origin re-requests its robots.txt and the Seed.
- [ ] 12.23 Docs: document warnings, the counted warnings, how a Crawl fails (stop reasons, exit codes, partial results), the network pause with its probes, outcomes, events and `--network-wait`, and the backstops in `docs/crawling.md`.
- [ ] 12.24 Review: run the code-review skill on group 12's commits, then refactor with the whole suite green.

## 13. Stopping with an interrupt (widening)

- [ ] 13.1 Drive "Ctrl+C stops a Crawl on macOS and Linux" at seam 1, subprocess, POSIX in CI.

  Done when: the signal handlers set the `StopSignal` through `loop.call_soon_threadsafe`, no `KeyboardInterrupt` reaches `010`'s runner during a Crawl, and the `stopped` end goes through `check_transition` with `interrupt`.
- [ ] 13.2 Drive "Ctrl+Break stops a Crawl on Windows (Windows)" at seam 1, subprocess, Windows in CI.
- [ ] 13.3 Drive "An interrupt is reported by one error" at seam 1, subprocess. Done when: `010`'s `interrupted` is the one error, with exit code 130.
- [ ] 13.4 **Guard:** "An interrupted Crawl keeps its queue", at seam 1, subprocess.
- [ ] 13.5 Drive "A request still running after the grace period is cancelled", fake timing. Done when: after the stop flag, requests in flight get 10 seconds of clock time and are then cancelled before their submit, so no unit is written for them.
- [ ] 13.6 Drive "A second interrupt ends the process at once" at seam 1, subprocess.
- [ ] 13.7 Docs: document interrupts, the grace period and the second interrupt in `docs/crawling.md`.
- [ ] 13.8 Review: run the code-review skill on group 13's commits, then refactor with the whole suite green.

## 14. Persistent frontier and continuing (widening)

- [ ] 14.1 **Guard:** "A killed Crawl leaves no half-recorded Page", at seam 1, subprocess, killed with `Popen.kill()`. Mark it `slow`.
- [ ] 14.2 Drive "Continuing a stopped Crawl completes it" at seam 2.

  Done when: the Crawl Service's continue operation (which `060`'s `resume` calls) accepts `stopped` and `failed` Crawls, goes back to `running` through `check_transition`, counts the URL limit over the Crawl's whole life, and inserts the `urls` row of a Seed that has none.
- [ ] 14.3 **Guard:** "Continuing does not request fetched URLs again", at seam 2.
- [ ] 14.4 Drive "Continuing clears how the Crawl ended" at seam 2, read by a handler registered for the test.
- [ ] 14.5 Drive "A failed Crawl is continued once its Seed answers" at seam 2. Done when: continuing re-queues `error` and `robots_unreachable` URLs.
- [ ] 14.6 Drive "Post-crawl passes run again after a continue" at seam 2.
- [ ] 14.7 Docs: document the frontier, what a killed Crawl keeps, and the continue operation for `060` in `docs/crawling.md`.
- [ ] 14.8 Review: run the code-review skill on group 14's commits, then refactor with the whole suite green.

## 15. Parsing with scripting on (waiting for selectolax)

- [ ] 15.1 Waits for the selectolax release that offers lexbor's scripting flag (an upstream pull request is being prepared). Page preparation parses with scripting on, as browsers and Google's renderer do, so a head `<noscript><img>` no longer ends `<head>`, and a head-noscript `<title>` stays inside its `<noscript>`. The Links of a body `<noscript>` are then found by fragment-parsing the text of each `<noscript>` (the user's ruling of 2026-10-14). Done when: the scripting-off cases of design Risks have scenarios that pass, and the body `<noscript>` Links of task 7.19 are still found.

## 16. Change check

- [ ] 16.1 Verify that every `#### Scenario:` in `specs/crawling/spec.md` has exactly one test named after it, with a small script over the test ids.
- [ ] 16.2 **Guard:** every code this change declares is listed by `spider commands` with its level and exit code, at seam 1.
- [ ] 16.3 Docs: the crawl pipeline section of `docs/architecture.md` says what is built (the context, the hooks, store-only units, page preparation behind the in-process executor), and `docs/schema.md` documents `urls`, `origins` and the new `crawl` columns, with their indexes and the values listed for later changes.
- [ ] 16.4 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 16.5 Review: run the code-review skill on the whole change against `specs/crawling/spec.md` and ADR-0006, then refactor with the whole suite green.
