## Why

`020-add-crawl-core` and `022-add-fetch-policy` fetch URLs, discover and follow Links and record how each URL responded, but nothing yet turns a fetched HTML document into the SEO data that agents, Rules and Reports work with. Screaming Frog's "Internal" tab is the record SEO people and agents already know. This change defines that record as stored, documented Page data, together with the attributes of every discovered Link. Rules (`040`), query Commands (`050`) and the Report (`070`) can then all read one set of columns with precise definitions.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships the minimum. **Deferred to v0.2:** Flesch Reading Ease, the Readability band and the syllable count; `--detect-language` and py3langid; SERP pixel widths; and raw HTML storage (`page_sources`, zstd, `--store-html/--no-store-html`).

- **New crawl-store tables.** Each follows the table conventions of `015-add-crawl-store`, is described column by column in `spider schema` and is documented in `docs/schema.md`. Every table and column is added in the TDD slice whose scenario first needs it.
  - `pages`: one row per Page. This is the flat Page record with all 94 Internal-tab columns: identity and response, titles and headings, directives, size, content, links and structured data.
  - `links`: one row per Link that `020-add-crawl-core` discovers, enriched with what analysis needs: the element and attribute, anchor or alt text, `rel` flags, the internal/external flag and the Content Area flag. The Link types are those of 020's Link type table.
  - `cookies`: one row per `Set-Cookie` header on a Page's response, whatever its status, with the name and attributes. The value is never stored.
  - `page_sources`: the HTML of Pages, stored as zstd frames.
- **Indexability and Indexability Status** for every Page, using fixed status codes: `blocked_by_robots_txt`, `redirected`, `client_error`, `server_error`, `noindex` and `canonicalised`.
- **Robots directives.** The directive columns store the raw text plus the noindex/nofollow verdicts of `020-add-crawl-core`'s robots directives parser. This change adds no parsing rules of its own.
- **Content Area.** By default it excludes `nav`, `header` and `footer`. It can be configured in a new `[content_area]` table in `spider.toml`, with `include` and `exclude` lists of CSS selectors.
- **Content metrics over the Content Area:**
  - Word Count, Sentence Count, Average Words per Sentence and syllable count
  - Flesch Reading Ease and a Readability band, for Pages that declare one of seven languages (en, de, es, fr, nl, pt, ru)
  - Text Ratio
  - the Exact Duplicate hash
- **SERP pixel widths** for titles (Arial 20 px) and meta descriptions (Arial 14 px), from a bundled table of Arial-metric character widths.
- **Structured data:** item counts and types for JSON-LD and Microdata, plus a count of JSON-LD blocks that fail to parse.
- **Link data:**
  - Inlink and outlink counts, including % of Total (`linking_pages_pct`). The inlink counts are computed in the post-crawl passes.
  - Folder Depth
  - Crawl Depth, copied from `urls`
- **Small additions beyond the Internal-tab list,** needed by Rules and agents:
  - `title_count`, `meta_description_count`, `h1_count`, `h2_count` and `canonical_count`
  - `canonical_url`, the URL that all canonical declarations agree on, and `canonical_relative`
  - per-source noindex/nofollow flags
  - `syllable_count`
  - `jsonld_parse_errors`
- **New `crawl` flags and their `spider.toml` equivalents under `[crawl]`:**
  - `--store-html` / `--no-store-html` (`store_html = true | false`). When unset, HTML is stored when the Crawl's `--max-urls` is from 1 to 50,000. The decision is made when the Crawl starts, recorded, and kept on resume.
  - `--detect-language` (`detect_language = false`) also stores the language detected from the Content Area text.
- **Columns measured by later releases** exist now and stay NULL:
  - `link_score` (v0.2)
  - `closest_similarity_pct` and `near_duplicate_count` (v0.3)
  - `structured_data_errors` and `structured_data_warnings` (v0.3)
  - `unique_js_inlinks`, `unique_js_outlinks` and `js_cookie_count` (v1.1)
- No new Commands or MCP tools. The new tables appear in `spider schema` and can be read with `spider sql`, `pages`, `page` and `export` (`050`).

## Capabilities

### New Capabilities
- `page-data`: the Page record (every Internal-tab column with its exact definition), Indexability, the Content Area and content metrics, readability, SERP pixel widths, the Exact Duplicate hash, structured-data counts, stored Link attributes and link counts, cookies, raw HTML storage, and the columns that stay NULL until later releases.

### Modified Capabilities
_None._ No specs exist yet. This change builds on requirements of `010`, `015`, `020` and `022` and does not modify them.

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

- **Depends on `010-add-workspace-and-cli-contract`** for `spider.toml` loading and flag > file > default precedence, `settings_invalid` errors, and the flag-mirroring rule for settings keys.
- **Depends on `015-add-crawl-store`** for:
  - the table conventions (names, units, timestamps, booleans, JSON, enumerations, NULL)
  - `docs/schema.md` and its contract test, `spider schema` and the transactional writer
  - migrations and the Crawl's recorded config
- **Depends on `020-add-crawl-core`** for:
  - the `urls` table: `is_internal`, `in_scope`, `fetch_state`, `content_type`, `parsed`, `blocked_by_robots`, `crawl_depth` and `fetched_at`
  - Link discovery and the Link type table, the robots directives parser and the extractor seam
  - the per-response hook, the post-crawl passes hook and the injectable clock
- **Depends on `022-add-fetch-policy`** for:
  - `redirect_url_id`, `size_bytes`, `transferred_bytes` and `content_encoding` on `urls`
  - `origins.http_version`
  - the redaction of cookie values in `response_headers`
  - the gzip fixture support
- **Works with `026-add-parse-pool`,** whose process pool runs this change's Page extractor. The extractor stays a pure function of its input.
- **Consumers:**
  - `040` evaluates Rules over `pages`, `links` and `urls`.
  - `050` exposes `pages`, `page`, `page --html` and `export`.
  - `060` records the new settings in the equivalent command, or warns when they cannot be written as flags.
  - `070` builds the Report.
  - `080` generates the Skill's column reference from the column descriptions.
- **Code:** `src/spider/extract/` (the Page extractor, content, readability, pixel widths, structured data, Link attributes), `src/spider/store/` (tables and migrations) and `docs/schema.md`.
- **Dependencies:**
  - `zstandard`, shared with `022-add-fetch-policy`
  - `py3langid`, imported only when `--detect-language` is set
  - a bundled character-width table derived from Liberation Sans (SIL OFL 1.1), which has the same advance widths as Arial
