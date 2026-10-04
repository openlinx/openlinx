> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

The motivation is in proposal.md. The exact column definitions are in `specs/page-data/spec.md`. This design covers how the data is produced and stored, and where the boundaries with the other changes lie ([ROADMAP.md](../../../ROADMAP.md), "What each change owns").

- **`010-add-workspace-and-cli-contract`:** `spider.toml` loading, `settings_invalid`, and flag > file > default precedence.
- **`015-add-crawl-store`:** the table conventions, `docs/schema.md` with its contract test, `spider schema`, the transactional writer, migrations and the Crawl's recorded config.
- **`020-add-crawl-core`:**
  - the `urls` table (the frontier, `is_internal`, `in_scope`, `fetch_state`, `content_type`, `parsed`, `blocked_by_robots`, `crawl_depth`, `fetched_at`)
  - Link discovery and the Link type table, and the robots directives parser
  - the extractor seam
  - two hooks: a **per-response hook** that runs for every recorded URL inside that URL's writer unit, and the **post-crawl passes** hook, which runs when a Crawl ends as `completed` or `stopped` and is safe to re-run
  - the injectable clock
- **`022-add-fetch-policy`:**
  - redirects hop by hop (`redirect_url_id`) and sizes (`size_bytes`, `transferred_bytes`, `content_encoding`)
  - `origins.http_version` (`http_1_1` / `http_2`)
  - `response_headers`, where cookie values are stored as `***`
  - the gzip fixture support
- **`026-add-parse-pool`:** it moves parsing into a process pool. This change's extractor must stay a pure, picklable function of its input.
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
- **How it is written.** `020`'s per-response hook writes the row in the URL's writer unit, from the same response, so the copies always agree. For an analysed Page, the hook adds the output of this change's Page extractor, which runs where `020` parses (in-process, or in `026`'s pool). For every other Page, the hook writes only the response-derived columns.
- *Alternative: normalised tables.* `pages` would hold only HTML-derived data, and consumers would join `urls`, or read a SQL view. Rejected: every consumer would need the join, namely `050`'s `--where` and `--fields`, `export`, the Report and agents writing SQL. Views would also complicate `spider schema` and `--where`.
- *Cost:* a few duplicated columns. The scenario "Repeated values equal the urls row" pins the agreement.

### D2. What is a Page, and which Pages are analysed
- **A Page** is a `urls` row with `is_internal` = 1, `in_scope` = 1, `fetch_state` = `fetched` and an HTML media type, whatever its status code. This follows the glossary ("returned an HTML document") and Screaming Frog's Internal → HTML filter.
- **An analysed Page** is exactly one that `020` parsed (`parsed` = 1): 2xx, and a body read in full.
- **Other Pages.** For 3xx, 4xx, 5xx and truncated Pages, the HTML columns stay NULL and they have no HTML Links. Link counts therefore aren't inflated by the navigation on error pages.
- *Alternative: exclude 3xx responses from Pages.* Rejected. It hides HTTP redirects from the Page record, which the Internal tab shows with Redirect URL and Type.

### D3. Indexability order and search-engine alignment
The order is: robots.txt, then status class, then noindex, then meta-refresh redirect, then canonicalised. A search engine first needs to be allowed to fetch the URL, then needs a usable response, then reads the directives. Four choices follow Google's documented behaviour rather than a simpler reading:
- All 2xx responses can be indexed, not only 200.
- Canonical declarations are read only from `<head>`, as the parser builds it. A stray `<img>` in `<head>` moves later elements into `<body>`, and a scenario pins that case. `020` still discovers `canonical` Links wherever they appear, so those are stored as Links but are not declarations.
- Conflicting canonical declarations give `canonical_url` NULL, which leaves the Page indexable.
- A meta refresh that names another URL counts as a redirect.

Indexability is stored only for Pages. `040`'s `canonical-to-non-indexable` Rule reads the stored value when the target is a Page. When the target is not a Page, it applies steps 1–4 of the same order to the target's `urls` row (see Open Questions).

### D4. Links: `020` discovers, `030` enriches
- **Owned by `020-add-crawl-core`:** Link discovery, the Link type table (including `srcset`, `prev`/`previous` and ignored references), the choice of which targets are requested, and a `urls` row for every target.
- **Added by this change:** the attributes that analysis needs, namely anchor text, `alt` text, `rel` flags, the Content Area flag, the element and attribute, and the target's internal flag. It stores one `links` row per discovered Link.
- **How rows are written.** Links from analysed Pages are enriched from the same parse, so HTML is never parsed twice. Links from the `Link` headers of responses that are not analysed Pages, such as a PDF's canonical header, are written through `020`'s per-response hook.
- **Tests.** Discovery behaviour is tested in `020`, not here. This change tests only the stored attributes, plus the contract that stored targets equal discovered targets.
- **Storage.** `links` stores URL ids, never URL text. Its natural key `(source_url_id, ordinal)` avoids a surrogate id. There are indexes on `target_url_id` and on `(type, target_url_id)`. Raw `href` values are not stored.

### D5. Robots directives come from `020`'s parser
`020-add-crawl-core` owns the robots directives parser, which covers meta robots and X-Robots-Tag, `none`, and values that apply only to a named crawler. `020` already needs it to honour page-level nofollow. This change stores the raw directive text in `meta_robots` and `x_robots_tag`, and the parser's noindex/nofollow verdicts in the four flag columns. It never re-parses directives.

### D6. Link counts
- Outlink counts are written with the analysed Page.
- Inlink counts and `linking_pages_pct` are computed in the **post-crawl passes**, through `020`'s hook. They use SQL aggregates over `links`, grouped by target and written in batches of about 10k Pages. They run for Crawls that end as `completed` or `stopped`, run again after `resume`, replace earlier results, and run before `040`'s passes.
- The counts follow Screaming Frog's documented definitions: anchor-element hyperlinks only, nofollow included, and % of Total relative to Pages with status 200.
- Self-links are excluded. Otherwise every Page listed in the navigation would count a link to itself, and its % of Total would read 100 %.
- *Alternative: incremental inlink counters updated for every Link write.* Rejected. It is contended, and it is wrong while targets are still unknown.

### D7. One text model for everything
- **Element text.** One algorithm produces headings, anchor text, the Content Area text, the Exact Duplicate hash and Text Ratio: text nodes in document order, with non-text elements skipped and block breaks at block-level elements and `br`.
- **Whitespace.** Normalisation follows `document.title` semantics (ASCII whitespace only), so NBSP is kept in stored text but still separates words.

### D8. Words, sentences and syllables
- **Words** are Unicode letter, mark and number runs, joined across a single `'`, `-`, `.` or `,`. Han, Hiragana and Katakana count one word per character. Scripts written without spaces between words (Thai, Lao, Khmer, Myanmar) are undercounted; this is documented as a limitation.
- **Syllables** are counted with our own rule-based counters per readability language, with no dictionary:
  - The base is groups of consecutive vowels, using each language's vowel set (including `y` for en and nl).
  - `en`: a final `e` is subtracted unless it ends a consonant + `le` or is the word's only vowel group.
  - `fr`: a final `e` or `es` is subtracted when the word has another vowel group.
  - `ru`: each vowel letter is one syllable, which is exact.
  - Every word counts at least 1 syllable.
  - `syllable_count` is stored so scores can be audited.
  - *Alternatives:* pyphen, which counts hyphenation points (not syllables, and it skips short words) and uses LGPL/MPL dictionaries; and CMUdict, which covers English only and is large. Both rejected.
- **Readability languages.** Spanish uses Szigriszt-Pazos (1993), because Fernández Huerta's (1959) published form is widely misquoted. Italian is left out until the Flesch–Vacca coefficients are verified, since two versions are in circulation.

### D9. SERP pixel widths
- **Data.** Widths come from a generated table of advance widths taken from **Liberation Sans Regular** (SIL OFL 1.1), which is metric-compatible with Arial. We avoid redistributing data taken from Arial's proprietary font files. The table ships as package data with the OFL notice.
- **Coverage.** Basic Latin, Latin-1, Latin Extended-A/B, Greek, Cyrillic and General Punctuation. Other characters use the fallback rules in the spec.
- **Font sizes.** 20 px for titles and 14 px for descriptions, the sizes Google uses on desktop results. The 561 px and 985 px limits are thresholds of `040`.
- *Alternative: measure text with a font engine (Pillow/FreeType).* Rejected. It adds a native dependency and makes results depend on the fonts installed.

### D10. Exact Duplicate hash
SHA-256 over the NFC-normalised Content Area text, stored as hex. It is in the standard library, stable across versions and collision-safe. The hash is NULL for Pages without words, so empty shells, such as client-rendered pages before v1.1, are not reported as one big duplicate group.

### D11. Raw HTML storage is decided when the Crawl starts
- **The decision.** It is made once, at start. The flags and `[crawl] store_html` win. Otherwise storage is on when `max_urls` is from 1 to 50,000, which includes the default of 10,000. The maintainer confirmed this rule on 2026-09-27.
- **Recording.** The decision is stored in the recorded config as `store_html` = `true` or `false`, and `resume` keeps it, even with a higher `--max-urls`. Coverage is therefore all or nothing per Crawl: `page_sources` has a row for every Page or for none, and no per-Page flag is needed.
  - *Alternative: store the first 50,000 Pages.* This was an earlier draft. Rejected, because partial coverage makes `page --html` unpredictable.
  - *Alternative: store everything and delete it all when the Crawl passes 50k.* Rejected as wasted work.
- **Compression.** Each Page is one independent zstd frame at level 3, using `zstandard` (also used by `022` for content decoding).
- **What is stored.** The bytes after content decoding, not a re-encoded string, so charset problems stay visible. `encoding` records the decoding result.
- **Name.** The table is called `page_sources`, a plural noun as `015` requires.

### D12. Language detection
`--detect-language` uses **py3langid** (BSD-3). It runs offline and is deterministic, covers about 97 languages, and its model is a few MB. It is imported only when the setting is on.
- *Alternatives:* lingua, whose wheels are very large; fastText lid.176, whose model is CC BY-SA and would put share-alike terms on redistribution; and langdetect, which is non-deterministic unless seeded.

### D13. Settings
- `store_html` and `detect_language` go under `[crawl]`, following `010`'s flag-mirroring rule. `020`'s generic recorded config therefore includes them.
- The new `[content_area]` table (`include`, `exclude`) is added to the settings model. Its effective values are recorded under `content_area`.
- Selectors are compiled when the settings are validated. An invalid one is a `settings_invalid` problem with the key `content_area.include` or `content_area.exclude`.
- `060`'s equivalent command warns that `[content_area]` cannot be written as flags.

### D14. Cookies without values
`cookies` stores only names and attributes, whatever the Page's status. It is written through `020`'s per-response hook. `022` stores cookie values in `response_headers` as `***`, so no cookie value exists anywhere in a crawl file.

### D15. Columns grow with their behaviours
There are no schema-first slices. Each column and table is added in the TDD slice whose scenario first needs it, with its `docs/schema.md` entry in the same commit, so `015`'s contract test is never red between commits. Scenarios are written so that every column is driven by a behaviour; for example, the second-title columns are asserted by "Second title element". The last slice adds the eight columns measured by later releases, and pins the full column set with "Schema lists exactly the Page record columns".

## Test seams

The seams come from [docs/testing.md](../../../docs/testing.md). No new seam is introduced:

- **Seam 4, pure-logic modules.** This includes the **Page extractor** entry point. It takes a response description (the URL, status, reason phrase, headers, body bytes, `020`'s discovered Links and robots verdicts, and the effective settings) and returns the Page columns, Link attributes and cookies. Other pure logic tested here: word, sentence and syllable counting, Flesch, pixel widths, Indexability, the Content Area, structured-data counting, and the HTML storage decision. All of it uses table-driven tests with the spec's literal expected values.
- **Seam 3+6, fixture site plus store contract.** End-to-end slices crawl fixture pages under `/pd/` and read `pages`, `links`, `cookies` and `page_sources` through a read-only connection, using only documented tables and columns. The fixture pages include a stored 46-byte gzip blob (`022`'s gzip support), a windows-1251 page, `Set-Cookie` on a 302, robots rules, and a four-Page link graph.
- **Seam 6, store contract.** `spider schema pages` and `spider schema links` are compared with hand-written expectations. Values are never auto-accepted from a snapshot.
- **Seam 1, CLI.** This covers the `crawl` flags (`--store-html`, `--no-store-html`, `--detect-language`), the `settings_invalid` error for a bad selector, and one real subprocess run on Windows with console code page 1251.
- **Boundary doubles.** Only the injectable clock, for `crawl_timestamp`. Neither aiohttp nor our own modules are mocked.

## Risks / Trade-offs

- [The duplicated response columns drift from `urls`] → They are written in one writer unit from one response, and a scenario compares them.
- [The `links` table grows large on big Crawls] → URL ids instead of text, a natural composite key, no raw `href`, and indexes limited to the two the post-crawl passes need. `026`'s benchmark includes the Link attributes.
- [Heuristic syllable counts are approximate] → Scores are documented as approximate, per-language word lists pin the rules, and `syllable_count` is stored for audit.
- [Excluding every `<header>` also drops article headers inside `<article>`] → This is the settled default. It can be changed with `exclude`, and the docs show how.
- [A resumed Crawl with a much higher `--max-urls` keeps storing HTML] → That is the documented consequence of deciding at start. `--no-store-html` cannot be changed on resume, so the docs recommend choosing it up front for large Crawls.
- [Our directive reading follows `020`'s parser, which can differ from Google's in edge cases] → Documented in `020`, with bot-specific directives listed under Open Questions.
- [Language detection is unreliable on short texts] → Detection is opt-in and returns NULL when there are no words. Readability never uses it.

## Migration Plan

The four tables are part of the squashed schema version 1 (before v0.1). There is no data to migrate and no rollback beyond reverting the change.

## Open Questions

These can be answered later without changing this change's specs or tasks:

1. **Indexability for Internal URLs that are not Pages.** This covers redirects without an HTML media type, URLs with no response, robots-blocked URLs and Resources. Storing it would mean new columns on `020`'s `urls` table. For now `040` applies steps 1–4 of the order to the target's `urls` row.
2. **Crawler-specific directives.** Should `<meta name="googlebot">` and X-Robots-Tag values prefixed with a user agent be honoured? That would be a change to `020`'s robots directives parser, following its `robots_user_agent` setting; the columns here would not change.
3. **More readability languages.** Italian (Flesch–Vacca) and others, once their coefficients are verified against the primary sources.
