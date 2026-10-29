## Why

`020-add-crawl-core` and `022-add-fetch-policy` fetch URLs, discover and follow Links and record how each URL responded, but nothing yet turns a fetched HTML document into the SEO data that agents, Rules and Reports work with. Screaming Frog's "Internal" tab is the record SEO people and agents already know. This change defines that record as stored, documented Page data, together with the attributes of every discovered Link. Rules (`040`), query Commands (`050`) and the Report (`070`) can then all read one set of columns with precise definitions.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships the minimum. **Deferred to v0.2:** Flesch Reading Ease, the Readability band and the syllable count; `--detect-language` and py3langid; SERP pixel widths; and raw HTML storage (`page_sources`, zstd, `--store-html/--no-store-html`). Their columns and the `page_sources` table exist in v0.1 and stay empty, so v0.2 fills them without a migration (ADR-0005). HTML storage is opt-in when it arrives (decided 2026-10-11: in the store benchmark, HTML was about 70% of the crawl file).

- **New crawl-store tables.** Each follows the schema conventions of `018-add-schema-conventions` (ADR-0005: a `STRICT` table, with CHECKs on its enumerations and flags), is described column by column in `linx schema` and is documented in `docs/schema.md`. Every table and column is added in the TDD slice whose scenario first needs it.
  - `pages`: one row per Page, keyed by `url_id`, with one unique index on `address`. This is the flat Page record of 96 columns, the Internal-tab columns and the small additions below: identity and response, titles and headings, directives, size, content, links and structured data.
  - `links`: one row per Link that `020-add-crawl-core` discovers, enriched with what analysis needs: the element and attribute, anchor or alt text, `rel` flags, where the Link was declared, its position on the Page (navigation, header, footer, sidebar or content) and, from v1.1, whether it came from the raw or the rendered HTML. The Link types are `020`'s `LinkType` list. A target's Internal flag is read from `urls`.
  - `cookies`: one row per `Set-Cookie` header on a Page's response, whatever its status, with the name and attributes. The value is never stored.
  - `page_sources`: the HTML of Pages, stored as zstd frames when HTML storage is turned on (v0.2). The table exists and is empty in v0.1.
- **Indexability and Indexability Status** for every Page, using fixed status codes: `blocked_by_robots_txt`, `redirected`, `client_error`, `server_error`, `noindex` and `canonicalised`.
- **Robots directives.** The directive columns store the raw text plus the noindex/nofollow verdicts of `020-add-crawl-core`'s robots directives parser. This change adds no parsing rules of its own.
- **Content Area.** By default it excludes `nav`, `header` and `footer`. It can be configured in a new `[content_area]` table in `openlinx.toml`, with `include` and `exclude` lists of CSS selectors.
- **Content metrics over the Content Area:**
  - Word Count, Sentence Count and Average Words per Sentence; **(v0.2)** the syllable count
  - **(v0.2)** Flesch Reading Ease and a Readability band, for Pages that declare one of seven languages (en, de, es, fr, nl, pt, ru)
  - Text Ratio
  - the Exact Duplicate hash
- **(v0.2) SERP pixel widths** for titles (Arial 20 px) and meta descriptions (Arial 14 px), from a bundled table of Arial-metric character widths.
- **Structured data:** item counts and types for JSON-LD and Microdata, plus a count of JSON-LD blocks that fail to parse.
- **Link data:**
  - Inlink and outlink counts, including % of Total (`linking_pages_pct`). The inlink counts are computed in the post-crawl passes.
  - Folder Depth
  - Crawl Depth, copied from `urls`
- **Small additions beyond the Internal-tab list,** needed by Rules and agents:
  - `title_count`, `meta_description_count`, `h1_count`, `h2_count` and `canonical_count`
  - `url_path` and `url_query`, the path and query of `address`
  - `canonical_url`, the URL that all canonical declarations agree on, and `canonical_relative`
  - per-source noindex/nofollow flags
  - `syllable_count`
  - `jsonld_parse_errors`
- **New `crawl` flags and their `openlinx.toml` equivalents under `[crawl]`, both from v0.2:**
  - `--store-html` / `--no-store-html` (`store_html = true | false`). HTML is not stored unless storage is turned on. The decision is made when the Crawl starts, recorded, and kept on resume.
  - `--detect-language` (`detect_language = false`) also stores the language detected from the Content Area text.
- **Columns measured by later releases** exist now and stay NULL:
  - the four SERP pixel widths, `syllable_count`, `flesch_reading_ease`, `readability`, `detected_language`, `link_score` and `http_version` (v0.2)
  - `closest_similarity_pct` and `near_duplicate_count` (v0.3)
  - `structured_data_errors` and `structured_data_warnings` (v0.3)
  - `unique_js_inlinks`, `unique_js_outlinks` and `js_cookie_count` (v1.1)
- No new Commands or MCP tools. The new tables appear in `linx schema` and can be read with `linx sql`, `pages`, `page` and `export` (`050`).

## Capabilities

### New Capabilities
- `page-data`: the Page record (every Internal-tab column with its exact definition), Indexability, the Content Area and content metrics, readability, SERP pixel widths, the Exact Duplicate hash, structured-data counts, stored Link attributes and link counts, cookies, raw HTML storage, and the columns that stay NULL until later releases.

### Modified Capabilities
_None._ This change builds on requirements of `010`, `015`, `017`, `018`, `020` and `022` and does not modify them.

## Non-goals

- Link Score: v0.2.
- Link graph views (`links --in|--out`) and Redirect Chain analysis (`redirects`): v0.2.
- Near-Duplicates (MinHash) and `duplicates`: v0.3. The two Near-Duplicate columns stay NULL.
- Structured-data validation and `structured-data`: v0.3. The validation columns stay NULL.
- Custom Extraction: v0.3.
- JavaScript rendering and the JS-only columns: v1.1.
- RDFa, spelling and grammar, accessibility, and more rich-result types: backlog.
- Link discovery, Link types and the robots directives parser belong to `020-add-crawl-core`. Redirects, sizes, HTTP version and `response_headers` belong to `022-add-fetch-policy`. Rules and Issues belong to `040-add-rules`. Query Commands, `page --html` and `export` belong to `050-add-query-and-segments`. The Report belongs to `070-add-html-report`.

## Impact

- **Depends on `010-add-workspace-and-cli-contract`** for `openlinx.toml` loading and flag > file > default precedence, `settings_invalid` errors, and the flag-mirroring rule for settings keys.
- **Depends on `015-add-crawl-store`** for:
  - the table conventions (names, units, timestamps, booleans, JSON, enumerations, NULL)
  - `docs/schema.md` and its contract test, `linx schema` and the transactional writer
  - the Crawl's recorded config
- **Depends on `017-speed-up-crawl-writer`** for `submit_async()` and its unit rules: deterministic units that return values only, and statements built once.
- **Depends on `018-add-schema-conventions`** (ADR-0005) for `public_table()` (`STRICT` tables, CHECKs from listed values and flags), references and indexes in `linx schema`, and the `Derived: ` and `Filled from v<major>.<minor>. ` description prefixes.
- **Depends on `020-add-crawl-core`** for:
  - the `urls` table: `is_internal`, `in_scope`, `fetch_state`, `content_type`, `parsed`, `blocked_by_robots_txt`, `crawl_depth` and `fetched_at`
  - Link discovery, `DiscoveredLink` and the `LinkType` list, the robots directives parser and page preparation with its extractors
  - the hooks: pure per-response handlers that return store rows, post-crawl passes that are store functions, and `default_hooks()` (its design D9 and D14)
  - the injectable clock
- **Depends on `022-add-fetch-policy`** for:
  - `redirect_url_id`, `size_bytes`, `transferred_bytes` and `content_encoding` on `urls`
  - `origins.http_version`
  - the redaction of cookie values in `response_headers`
  - the gzip fixture support
- **Works with `026-add-parse-pool`** (v0.1): page preparation, and this change's Page extractor with it, runs in its process pool. The extractor stays a pure, module-level function of its input.
- **Consumers:**
  - `040` evaluates Rules over `pages`, `links` and `urls`.
  - `050` exposes `pages`, `page`, `page --html` and `export`.
  - `060` records the new settings in the equivalent command, or warns when they cannot be written as flags.
  - `070` builds the Report.
  - `080` generates the Skill's column reference from the column descriptions.
- **Code:** `src/openlinx/extract/` (the Page extractor, content, readability, pixel widths, structured data, Link attributes), `src/openlinx/store/` (`openlinx.store.pages` and `openlinx.store.links`: the tables, their row values and writers, and the inlink pass) and `docs/schema.md`.
- **Dependencies:**
  - `zstandard` (v0.2), shared with `022-add-fetch-policy`
  - `py3langid` (v0.2), imported only when `--detect-language` is set
  - (v0.2) a bundled character-width table derived from Liberation Sans (SIL OFL 1.1), which has the same advance widths as Arial
