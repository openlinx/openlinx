> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

The motivation is in proposal.md. The exact column definitions are in `specs/page-data/spec.md`. This design covers how the data is produced and stored, and where the boundaries with the other changes lie ([ROADMAP.md](../../../ROADMAP.md), "What each change owns").

- **`010-add-workspace-and-cli-contract`:** `spider.toml` loading, `settings_invalid`, and flag > file > default precedence.
- **`015-add-crawl-store`:** the table conventions, `docs/schema.md` with its contract test, `spider schema`, the transactional writer and the Crawl's recorded config.
- **`017-speed-up-crawl-writer`:** units go through `submit_async()` and may run twice, so each follows `017` D7 (deterministic, values only, checked with `replay_now(writer)` in seam-2 tests) and `017` D9 (statements built once, at import).
- **`018-add-schema-conventions` and ADR-0005:** every table is declared through `018`'s `public_table()`, so it is `STRICT` and its enumerations and flags get CHECKs; `spider schema` lists references and indexes, and the contract test compares them. The schema blueprint of 2026-10-11 and its rulings decide this change's tables.
- **`020-add-crawl-core`:**
  - the `urls` table (the frontier, `is_internal`, `in_scope`, `fetch_state`, `content_type`, `parsed`, `blocked_by_robots_txt`, `crawl_depth`, `fetched_at`)
  - Link discovery, its `DiscoveredLink` values and the `LinkType` list in `spider.store.records`, and the robots directives parser. This change reads the `DiscoveredLink` values from `links_in_tree(...)` (`spider.crawl.links`) on page preparation's tree, and `base_url(tree, url, encoding)` gives the base it resolves its own references against; the bytes wrapper `extract_links` stays for tests
  - page preparation (`020` D9): `prepare_page(url, response, settings)` in `spider.crawl.pages`, one pure function of a fetched response that decodes, parses once and runs the registered extractors, in-process or in `026`'s pool
  - the hooks of `020` D9 and D14: `Hooks` in `spider.crawl.hooks` (extractors, handlers, passes and `row_writers`), listed in `default_hooks()`, which `020` keeps in its composition root `spider.services.hooks`, so `spider.crawl` knows none of its plugins. A **per-response handler** is a pure function from the URL's `UrlResult` (its row values: `url_id`, `url`, `crawl_depth`, `discovered_via`, `found_on_url_id`, `fetch_state`, `skip_reason`, `fetch_error`, the status, the headers, `parsed`, `parse_error` and the extractor `outputs`) to any iterable of store rows, all or none: a handler that fails midway keeps none. The URL's writer unit writes each row through the row writer registered for its type (`spider.store.rows.write_rows`); a **post-crawl pass** is a store function that submits its own units. Passes run when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written, and again after every continued run, so they must be safe to re-run.
  - `is_html_type(content_type)` in `spider.crawl.pages`, the one rule of an HTML response, which page preparation and the Page predicate share
  - the injectable clock
- **`022-add-fetch-policy`:**
  - redirects hop by hop (`redirect_url_id`) and sizes (`size_bytes`, `transferred_bytes`, `content_encoding`)
  - `origins.http_version` (`http_1_1` / `http_2`), filled from v0.2
  - `response_headers`, where cookie values are stored as `***`
  - the gzip fixture support
- **`026-add-parse-pool`:** page preparation runs in its process pool in v0.1, so this change's extractor must stay a pure, module-level function of its input, with a msgspec result that crosses the process boundary.
- **v0.1 scope (ROADMAP.md):** syllables and readability (D8), SERP pixel widths (D9), raw HTML storage (D11) and language detection (D12) arrive in v0.2. Their columns, and the `page_sources` table, exist in v0.1 and stay NULL or empty (ADR-0005), so v0.2 changes no table.
- **Scale target:** about 500k URLs and tens of millions of Link rows in one SQLite file ([ADR-0003](../../../docs/adr/0003-sqlalchemy-core-not-orm.md)).

## Goals / Non-Goals

**Goals:**
- One flat, documented Page record per Page that agents can query without joins.
- Deterministic values: the same HTML gives the same numbers on every OS, whatever fonts or locale are installed.
- One parse per Page, and no second implementation of anything `020` already owns (Link discovery, Link types, robots directives).
- Page data that is readable while the Crawl runs. Only the inlink columns wait for the post-crawl passes.

**Non-Goals:**
- Reproducing Screaming Frog's numbers exactly. Where its definitions are undocumented, we define our own and document them.
- Re-analysing stored HTML after a Crawl, for example when the Content Area settings change. The settings apply to Crawls started after the change.
- Rules, Issues and the Health Score, which belong to `040-add-rules`.

## Decisions

### D1. The Page record is one flat table that repeats response values
`pages` holds every Internal-tab column, including values that `urls` and `origins` already hold: status code, content type, sizes, response time, `fetched_at`, HTTP version and Crawl Depth.
- **How it is written.** This change's per-response handler is a pure function from the URL's `UrlResult` to store rows (`020` D9): a Page row, its Link rows and its cookie rows. The handler is `spider.extract.page_handler`. The rows are frozen dataclasses (`kw_only`, with slots) declared in `spider.store.page_records`, which loads no sqlalchemy. The tables are declared in `spider.store.schema`, the only definition of the schema; `spider.store.pages` and `spider.store.links` write them and register the writer of each row type in `row_writers`, and the URL's writer unit writes the rows together with the URL's own row (`020` D14), so the copies always agree. For an analysed Page, the handler reads the output of this change's Page extractor, `spider.extract.page_data`, which imports only `spider.crawl.pages` and the pure text helpers of `spider.extract`, so `026`'s workers never load sqlalchemy (a test lists the modules a fresh process loads with it). It runs inside page preparation (in-process, or in `026`'s pool) over the parsed tree and `020`'s `PageInput`; this change adds `content_area` to page preparation's settings snapshot. For every other Page, it builds only the response-derived columns.
- *Alternative: normalised tables.* `pages` would hold only HTML-derived data, and consumers would join `urls`, or read a SQL view. Rejected: every consumer would need the join, namely `050`'s `--where` and `--fields`, `export`, the Report and agents writing SQL. Views would also complicate `spider schema` and `--where`.
- *Cost:* a few duplicated columns. The scenario "Repeated values equal the urls row" pins the agreement.

### D2. What is a Page, and which Pages are analysed
- **A Page** is a `urls` row with `is_internal` = 1, `in_scope` = 1, `fetch_state` = `fetched` and an HTML media type, whatever its status code. This follows the glossary ("returned an HTML document") and Screaming Frog's Internal → HTML filter.
- **An analysed Page** is exactly one that `020` parsed (`parsed` = 1): 2xx, and a body read in full.
- **A Page whose Page extractor failed** (the user's decision of 2026-10-14) is still analysed. `020` follows its Links and records `parsed` = 1 with `parse_error` = `extractor_error`, and `parse_error_message` names the extractor. Only the HTML-derived columns of the failed extractor are NULL: the title and heading, content and structured-data columns, and the Link attributes this change adds. `indexability`, the directive columns and `canonical_url` come from `020`'s records, so they stay exact: the handler takes the robots directives verdicts (`020`'s directives parser, which never raises, D5) and the canonical, pagination, AMP, mobile-alternate and refresh Links (`020`'s link extractor) from `PageInput` and the prepared record, never from this change's extractor output, and robots.txt and the status from `urls`. Its `links` rows are stored from `020`'s `DiscoveredLink` values, and its outlink columns are counted from them. `parse_error` says why the columns are missing, and `040`'s Rules never fire on a NULL column. `parsed` = 0 means nothing came out: decoding or parsing failed, or `026`'s worker crashed or timed out.
- **Other Pages.** For 3xx, 4xx, 5xx and truncated Pages, the HTML columns stay NULL and they have no HTML Links. Link counts therefore aren't inflated by the navigation on error pages.
- *Alternative: exclude 3xx responses from Pages.* Rejected. It hides HTTP redirects from the Page record, which the Internal tab shows with Redirect URL and Type.

### D3. Indexability order and search-engine alignment
The order is: robots.txt, then status class, then noindex, then a refresh redirect, then canonicalised. A search engine first needs to be allowed to fetch the URL, then needs a usable response, then reads the directives. Four choices follow Google's documented behaviour rather than a simpler reading:
- All 2xx responses can be indexed, not only 200.
- Canonical declarations are read only from `<head>`, as the parser builds it. A stray `<img>` in `<head>` moves later elements into `<body>`, and a scenario pins that case. `020` still discovers `canonical` Links wherever they appear, so those are stored as Links but are not declarations.
- Conflicting canonical declarations give `canonical_url` NULL, which leaves the Page indexable.
- A meta refresh or an HTTP `Refresh` header that names another URL counts as a redirect, as `020`'s `meta_refresh` and `http_refresh` Link types do.

Indexability is stored only for Pages. `040`'s `canonical-to-non-indexable` Rule reads the stored value when the target is a Page. When the target is not a Page, it applies steps 1–4 of the same order to the target's `urls` row (see Open Questions).

### D4. Links: `020` discovers, `030` enriches
- **Owned by `020-add-crawl-core`:** Link discovery, the Link type table (including `srcset`, `prev`/`previous` and ignored references), the choice of which targets are requested, and a `urls` row for every target. A malformed or non-http(s) reference gives no Link (`020` D5); if this change ever needs raw values, it reads them from the same parsed tree.
- **Added by this change:** the attributes that analysis needs, namely anchor text, `alt` text, `rel` flags (from `DiscoveredLink.rel`, lower-cased ASCII tokens), the element and attribute, where the Link was declared (`declared_in`, the field `020` names), its position on the Page (`link_position`) and, from v1.1, whether it came from the raw or the rendered HTML (`html_source`). It stores one `links` row per discovered Link.
- **How rows are written.** Links from analysed Pages are enriched from the same parse, so HTML is never parsed twice. The handler also returns the Links that `020` discovers in the `Link` and `Refresh` headers of responses that are not analysed Pages, such as a PDF's canonical header. The Link attributes reach the handler nested in the Page extractor's output, as one tuple of per-Link records, never as fields of their own: the handler spreads the extractor's other fields into the Page row, and the test that every extracted field has a `pages` column (group 2) would fail on a Link field spread there.
- **Tests.** Discovery behaviour is tested in `020`, not here. This change tests only the stored attributes, plus the contract that stored targets equal discovered targets.
- **Storage.** `links` stores URL ids, never URL text. Its natural key `(source_url_id, ordinal)` avoids a surrogate id. The ordinal is `DiscoveredLink.ordinal` as `020` numbers it (from 1, header Links first); this change never renumbers. There are indexes on `target_url_id` and on `(type, target_url_id)` until the links benchmark (task 10.1) chooses the layout and indexes (ADR-0005); the documented columns do not depend on that choice. On the chosen layout, `017`'s throughput check runs once at 20k Pages and restates its floor (task 10.11). Raw `href` values are not stored.
- **No copies in `links`** (ruling Q8 of the schema blueprint): the target's Internal flag is `urls.is_internal`, joined on `target_url_id`, and a Link in the Content Area is read as `link_position = 'content'`. Each copy would have been written for tens of millions of rows.
- **Link position** is `head` for a Link in `<head>`, and otherwise comes from the nearest enclosing `nav`, `header`, `footer` or `aside` element, so it needs no settings and does not move when `[content_area]` changes. Only a Link declared in an HTTP header has none.
  - *Alternative:* class and id patterns such as `menu` or `sidebar`. Rejected: they guess, and a guessed value in a column with fixed values is hard to correct later.

### D5. Robots directives come from `020`'s parser
`020-add-crawl-core` owns the robots directives parser, which covers meta robots and X-Robots-Tag, `none`, and values that apply only to a named crawler. `020` already needs it to honour page-level nofollow. This change stores the raw directive text in `meta_robots` and `x_robots_tag`, and the parser's noindex/nofollow verdicts in the four flag columns. It never re-parses directives.

### D6. Link counts
- Outlink counts are written with the analysed Page. The handler counts them in Python from the Page's `DiscoveredLink` values, each of which carries its target's `is_internal`, which page preparation sets from the Scope in its settings snapshot (`020` D5, D9). No statement runs for them. `set_cookie_count` is counted by the handler from the response's `Set-Cookie` headers.
  - *Alternative: count the Links in the Page's unit, over `links` and `urls.is_internal`.* One more query per Page on the writer's hot path. Rejected, since the Scope is host-based and page preparation already has it.
- Inlink counts and `linking_pages_pct` are computed by a **post-crawl pass**, a store function in `spider.store.links` that `default_hooks()` in `spider.services.hooks`, the composition root, lists before `040`'s pass. It uses SQL aggregates over `links`, grouped by target, and submits units of about 10k Pages, whose statements are built once (`017` D9) and which give the same rows when run twice (`017` D7). It runs for Crawls that end as `completed` or `stopped`, runs again after `resume`, and replaces earlier results.
- The counts follow Screaming Frog's documented definitions: anchor-element hyperlinks only, nofollow included, and % of Total relative to Pages with status 200.
- Self-links are excluded. Otherwise every Page listed in the navigation would count a link to itself, and its % of Total would read 100 %.
- *Alternative: incremental inlink counters updated for every Link write.* Rejected. It is contended, and it is wrong while targets are still unknown.

### D7. One text model for everything
- **Element text.** One algorithm produces headings, anchor text, the Content Area text, the Exact Duplicate hash and Text Ratio: text nodes in document order, with non-text elements skipped and block breaks at block-level elements and `br`.
- **Whitespace.** Normalisation follows `document.title` semantics (ASCII whitespace only), so NBSP is kept in stored text but still separates words.

### D8. Words, sentences and syllables
- **Words** are Unicode letter, mark and number runs, joined across a single `'`, `-`, `.` or `,`. Han, Hiragana and Katakana count one word per character. Scripts written without spaces between words (Thai, Lao, Khmer, Myanmar) are undercounted; this is documented as a limitation.
- **Syllables** (v0.2) are counted with our own rule-based counters per readability language, with no dictionary:
  - The base is groups of consecutive vowels, using each language's vowel set (including `y` for en and nl).
  - `en`: a final `e` is subtracted unless it ends a consonant + `le` or is the word's only vowel group.
  - `fr`: a final `e` or `es` is subtracted when the word has another vowel group.
  - `ru`: each vowel letter is one syllable, which is exact.
  - Every word counts at least 1 syllable.
  - `syllable_count` is stored so scores can be audited.
  - *Alternatives:* pyphen, which counts hyphenation points (not syllables, and it skips short words) and uses LGPL/MPL dictionaries; and CMUdict, which covers English only and is large. Both rejected.
- **Readability languages** (v0.2). Spanish uses Szigriszt-Pazos (1993), because Fernández Huerta's (1959) published form is widely misquoted. Italian is left out until the Flesch–Vacca coefficients are verified, since two versions are in circulation.

### D9. SERP pixel widths (v0.2)
- **Data.** Widths come from a generated table of advance widths taken from **Liberation Sans Regular** (SIL OFL 1.1), which is metric-compatible with Arial. We avoid redistributing data taken from Arial's proprietary font files. The table ships as package data with the OFL notice.
- **Coverage.** Basic Latin, Latin-1, Latin Extended-A/B, Greek, Cyrillic and General Punctuation. Other characters use the fallback rules in the spec.
- **Font sizes.** 20 px for titles and 14 px for descriptions, the sizes Google uses on desktop results. The 561 px and 985 px limits are thresholds of `040`.
- *Alternative: measure text with a font engine (Pillow/FreeType).* Rejected. It adds a native dependency and makes results depend on the fonts installed.

### D10. Exact Duplicate hash
SHA-256 over the NFC-normalised Content Area text, stored as hex. It is in the standard library, stable across versions and collision-safe. The hash is NULL for Pages without words, so empty shells, such as client-rendered pages before v1.1, are not reported as one big duplicate group.

### D11. Raw HTML storage is opt-in, decided when the Crawl starts (v0.2)
- **The decision.** It is made once, at start. `--store-html` and `--no-store-html`, then `[crawl] store_html`, decide; when none is set, HTML is not stored (decided 2026-10-11: in the store benchmark, HTML was about 70% of the crawl file).
  - *Alternative: store HTML automatically when `--max-urls` is from 1 to 50,000,* as an earlier draft had. Rejected: `--max-urls` has no default limit since 2026-10-10, so the rule stored nothing by default, and storage then depended on a limit chosen for another reason.
- **The table exists from v0.1** (ruling Q10 of the schema blueprint) and stays empty, so turning storage on changes no table and no contract.
- **Recording.** The decision is stored in the recorded config as `store_html` = `true` or `false`, and `resume` keeps it. Coverage is therefore all or nothing per Crawl: `page_sources` has a row for every Page or for none, and no per-Page flag is needed.
  - *Alternative: store the first 50,000 Pages.* This was an earlier draft. Rejected, because partial coverage makes `page --html` unpredictable.
- **Compression.** Each Page is one independent zstd frame at level 3, using `zstandard` (also used by `022` for content decoding).
- **What is stored.** The bytes after content decoding, not a re-encoded string, so charset problems stay visible. `encoding` records the decoding result.
- **Name.** The table is called `page_sources`, a plural noun as `015` requires.

### D12. Language detection (v0.2)
`--detect-language` uses **py3langid** (BSD-3). It runs offline and is deterministic, covers about 97 languages, and its model is a few MB. It is imported only when the setting is on.
- *Alternatives:* lingua, whose wheels are very large; fastText lid.176, whose model is CC BY-SA and would put share-alike terms on redistribution; and langdetect, which is non-deterministic unless seeded.

### D13. Settings
- From v0.2, `store_html` and `detect_language` go under `[crawl]`, following `010`'s flag-mirroring rule. `020`'s generic recorded config therefore includes them.
- The new `[content_area]` table (`include`, `exclude`) is added to the settings model. Its effective values are recorded under `content_area`.
- Selectors are compiled when the settings are validated. An invalid one is a `settings_invalid` problem with the key `content_area.include` or `content_area.exclude`.
- `060`'s equivalent command warns that `[content_area]` cannot be written as flags.

### D14. Cookies without values
`cookies` stores only names and attributes, whatever the Page's status: `020` calls the handler for every URL that reaches a final state, and the handler returns the cookie rows of every Page. `022` stores cookie values in `response_headers` as `***`, so no cookie value exists anywhere in a crawl file.

### D15. Columns grow with their behaviours
There are no schema-first slices. Each column and table is added in the TDD slice whose scenario first needs it, with its `docs/schema.md` entry in the same commit, so `015`'s contract test is never red between commits. Scenarios are written so that every column is driven by a behaviour; for example, the second-title columns are asserted by "Second title element". The last v0.1 slice adds the 17 `pages` columns and `links.html_source` that later releases fill, and pins the full column set with "Schema lists exactly the Page record columns".

### D16. The tables under ADR-0005
The schema blueprint of 2026-10-11 and its rulings decide the four tables. `018`'s `public_table()` and contract test enforce what a test can; the review checks the rest of ADR-0005.
- **Declaration:** each table goes through `018`'s `public_table()`, so it is `STRICT` and its enumerations and flags get CHECKs. The value lists are `Literal`s in `spider.store.page_records`, which loads no sqlalchemy, as `020`'s `LinkType` is, so the code, the CHECK and `values` cannot disagree. Values that a later release writes are listed from v0.1: `redirect_type`'s `javascript_redirect` (v1.1), `html_source` (v1.1), the readability bands (v0.2) and `http_version` (v0.2).
- **Types:** the spec's column tables give every column's type and nullability. Fractional values (`average_words_per_sentence`, `text_ratio_pct`, `linking_pages_pct`, `flesch_reading_ease`, `closest_similarity_pct` and `link_score`) are `REAL`, declared with `sqlalchemy.REAL`: `Float` renders `FLOAT`, which a `STRICT` table refuses. A `pages` column that every Page has is NOT NULL; an HTML column is nullable, because a Page that is not analysed has none.
- **Kinds:** the inlink columns are derived (D), written only by the inlink pass (D6). The later columns (N) exist from v0.1, NULL. The W columns repeat what other rows determine and are written in the Page's unit (D1): the address forms, the response copies, Indexability, the redirect columns, `folder_depth`, `set_cookie_count` and the outlink counts. `set_cookie_count` and the outlink counts count rows of `cookies` and `links`, which ADR-0005 would not store, but they are Screaming Frog columns (rule 14) that every consumer reads from the flat record (D1).
- **Names:** Screaming Frog's names stay, `cookies.expires` and `cookies.max_age` included, with their units in their descriptions (ruling Q9). `links.declared_in` (`html`, `http_header`) and `links.html_source` (`raw`, `rendered`) keep `origin` for scheme, host and port only (ruling Q7).
- **Keys and layout:** `pages.url_id` and `page_sources.url_id` are INTEGER PRIMARY KEYs, rowid aliases that reference `urls.id`. `cookies` is keyed by `(url_id, ordinal)` and `WITHOUT ROWID`: its rows are narrow and read only by `url_id`, a key prefix. `links` is keyed by `(source_url_id, ordinal)`; its layout waits for the links benchmark.
- **Indexes:** `pages` has only the unique `pages_address` (ruling Q6). `050`'s sorts and `--where` scan `pages`; `080` documents that cost (about a second at 500k Pages), and `026`'s 500k run is where it is revisited. `cookies` and `page_sources` need no index beyond their keys.

### D17. Every column a Rule reads is stored
`040`'s Rules are only SQL queries over stored columns (user decision, 2026-10-11), so a value a Rule needs must be a column of this change. The v0.1 Rules read `title_count`, `title_1`, `title_1_length`, `meta_description_count`, `meta_description_1`, `h1_count`, `h1_1`, `meta_robots_noindex`, `x_robots_tag_noindex`, `canonical_url`, `indexability` and `indexability_status`, all v0.1 columns; `canonical-to-non-indexable` also reads the target's `urls` row when the target is not a Page (D3). The v0.2 Rules also read the pixel widths, `word_count`, `content_hash`, `url_encoded_address`, and `links.element`, `attribute` and `alt_text`. The URL Rules (v0.2) read `url_path` and `url_query`, the path and query of `address`, stored as W columns (ruling of 2026-10-11) because agents' SQL filters on them too. Cut from `address`, they hold non-ASCII characters decoded, which `urls.url` holds only as `%XX` escapes.

## Test seams

The seams come from [docs/testing.md](../../../docs/testing.md). No new seam is introduced:

- **Seam 4, pure-logic modules.** This includes the **Page extractor**, which takes the parsed tree and `020`'s frozen `PageInput` (the response URL, status, headers, the decoded document's length, the `DiscoveredLink` values, the robots directives and the settings snapshot of the worker, received once at its start (`020` D9), with `content_area`) and returns the HTML-derived columns and Link attributes, and the **Page handler**, which takes a `UrlResult` and returns the Page, Link and cookie rows. Other pure logic tested here: word, sentence and syllable counting, Flesch, pixel widths, Indexability, the Content Area, structured-data counting, and the HTML storage decision. All of it uses table-driven tests with the spec's literal expected values. A test of the Page extractor runs `020`'s `prepare_page` over the HTML as bytes, with the Page extractor in its settings, then the Page handler over the resulting `UrlResult`, and asserts the Page row, so one pure test covers the decoding, the extractor and the handler's mapping to the column. "URL blocked by robots.txt is not a Page" and "URL without a response is not a Page" run here too, on the `UrlResult` that `020` records for each; `020`'s task 10.5 and `022`'s timeout scenario pin those records end to end.
- **Seam 3+6, fixture site plus store contract.** End-to-end slices crawl fixture pages under `/pd/` and read `pages`, `links`, `cookies` and `page_sources` through a read-only connection, using only documented tables and columns. "External HTML response is not a Page" reaches a second fixture site instance through `020`'s DNS resolver hook. The fixture pages include a stored 46-byte gzip blob (`022`'s gzip support), a windows-1251 page, `Set-Cookie` on a 302, robots rules, and a four-Page link graph.
- **Seam 2, services and store API.** `spider.store.pages` and `spider.store.links` over a real crawl store: each row writer and the inlink pass, with `017`'s `replay_now(writer)` forcing a replay, so a unit that runs twice writes the same rows.
- **Seam 6, store contract.** `spider schema pages` and `spider schema links` are compared with hand-written expectations: the column tables of the spec, and the index `pages_address`. Values are never auto-accepted from a snapshot.
- **Seam 1, CLI.** This covers the `crawl` flags (`--store-html`, `--no-store-html`, `--detect-language`), the `settings_invalid` error for a bad selector, and one real subprocess run on Windows with console code page 1251.
- **Boundary doubles.** Only the injectable clock, for `crawl_timestamp`. Neither aiohttp nor our own modules are mocked.

## Risks / Trade-offs

- [The duplicated response columns drift from `urls`] → They are written in one writer unit from one response, and a scenario compares them.
- [The `links` table grows large on big Crawls] → URL ids instead of text, a natural composite key, no raw `href`, and indexes limited to the two the post-crawl passes need. `026`'s benchmark includes the Link attributes.
- [Heuristic syllable counts are approximate] → Scores are documented as approximate, per-language word lists pin the rules, and `syllable_count` is stored for audit.
- [`link_position` reads only elements, so a site that marks its navigation with classes rather than `nav`, `header`, `footer` or `aside` gets `content` for it] → Class and id patterns are a possible v0.2 refinement, for sites without semantic elements.
- [Excluding every `<header>` also drops article headers inside `<article>`] → This is the settled default. It can be changed with `exclude`, and the docs show how.
- [A Crawl started without `--store-html` has no HTML for `page --html` (v0.2)] → The decision is made at start and kept on resume, so the docs say to choose it up front.
- [Our directive reading follows `020`'s parser, which can differ from Google's in edge cases] → Documented in `020`, with bot-specific directives listed under Open Questions.
- [Language detection is unreliable on short texts] → Detection is opt-in and returns NULL when there are no words. Readability never uses it.
- [Tests of group 1 named after no scenario, which the scenario count ignores] → In `tests/store/test_pages.py`: `test_the_units_of_pages_run_again_the_same`, which replays a URL's unit with its Page row with `replay_now` (task 1.1; through `record_fetched`, with the two address forms distinct, since the review of group 1); in `tests/extract/test_page_handler.py`: `test_an_address_keeps_what_does_not_decode` (a punycode label that does not decode, a port, an escaped byte that is no UTF-8, a cut UTF-8 sequence and an escaped ASCII character stay as requested; task 1.2) and `test_an_internal_url_outside_the_scope_is_not_a_page` (`in_scope` = 0 with `is_internal` = 1, as a Section Crawl of `020`'s group 8 records; task 1.6); from the review of group 1, in `tests/extract/test_page_handler.py`: `test_a_url_without_a_response_is_no_page_whatever_its_content_type` (the Page predicate reads `fetch_state` itself, not only the content type that today only a fetched URL has), and in `tests/extract/test_addresses.py`: `test_an_address_normalises_back_to_its_url`, a hypothesis property, so two distinct URLs never share an address, which the unique `pages_address` needs.
- [Tests of group 2 named after no scenario, which the scenario count ignores] → In `tests/extract/test_page_data.py`: `test_a_no_break_space_stays_in_a_title` (task 2.2; red by mutation: normalising with `str.split`, which splits at a no-break space, fails it) and `test_a_title_in_math_is_ignored` (task 2.3); from the review of group 2: `test_the_page_extractor_never_raises`, a hypothesis property over bytes and repaired markup, in `tests/extract/test_page_data.py`; `test_the_page_extractor_loads_no_sqlalchemy`, which lists what a fresh process loads with the extractor, in `tests/extract/test_imports.py`; and `test_the_page_row_has_every_pages_column_and_every_extracted_field` in `tests/store/test_pages.py`, since the handler spreads the extractor's output into the Page row, so a field missing on either side would otherwise stay NULL without a failure.
- [Tests of group 3 named after no scenario, which the scenario count ignores] → In `tests/extract/test_page_data.py`: `test_a_meta_description_without_content_is_empty` (with a name in spaces) and `test_a_meta_description_in_noscript_is_ignored` (task 3.1; red by mutation: the name left untrimmed, and the metas taken without the ancestor rule), `test_heading_text_leaves_out_scripts_and_styles` and `test_a_heading_in_noscript_is_ignored` (task 3.4; red by mutation: the walker without its skip list, and the headings taken without the ancestor rule), and `test_block_elements_separate_heading_words` (task 3.5).
- [Page preparation parses with scripting off, as lexbor does, while browsers and a search engine's renderer parse with scripting on, where everything inside `noscript` is raw text] → In `<head>`, the parser closes a `noscript` at the first element that a head `noscript` may not hold: a `<title>` there is moved out of it, so no ancestor test can see it, and an `<img>` there, as tracking-pixel snippets have, ends `<head>`, so every later head element, such as the canonical, the meta description or meta robots, lands in `<body>`. Inside `<body>`, the `noscript` ancestor rule already holds. The fix is that page preparation parses with scripting on once selectolax offers it (the user's decision of 2026-10-14: an upstream option); task 12.4 then drives "Title in head noscript is ignored".
- [Which characters stay encoded in `address` comes from Python's Unicode database, which a new Python version extends] → Only the categories of assigned characters are read (no `Cn` or `Co`), so an address changes only if a character's category changes; the property above pins that an address still normalises back to its URL.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds `pages`, `links`, `cookies` and `page_sources` to the declared schema and to `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5).

## Open Questions

These can be answered later without changing this change's specs or tasks:

1. **Indexability for Internal URLs that are not Pages.** This covers redirects without an HTML media type, URLs with no response, robots-blocked URLs and Resources. Storing it would mean new columns on `020`'s `urls` table. For now `040` applies steps 1–4 of the order to the target's `urls` row.
2. **Crawler-specific directives.** Should `<meta name="googlebot">` and X-Robots-Tag values prefixed with a user agent be honoured? That would be a change to `020`'s robots directives parser, following its `robots_user_agent` setting; the columns here would not change.
3. **More readability languages.** Italian (Flesch–Vacca) and others, once their coefficients are verified against the primary sources.
