> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task is one red → green slice and one commit (see docs/testing.md).
- **Red:** write the failing test for the named scenario at the named seam and watch it fail for the right reason.
- **Green:** write only the code that makes it pass, then run the whole suite.

Seams: 1 CLI, 2 services and store API, 4 pure-logic modules (including the Page extractor), 6 store contract. "Seam 3+6" means crawl the fixture site, then read the documented tables read-only.

There are no schema-first slices. A table or column is added in the slice whose scenario first needs it, through `018`'s `public_table()` (`STRICT`, and CHECKs from the declared values and flags), with its description and its `docs/schema.md` entry in the same commit, so the contract test (`015`'s, extended by `018`) is never red between commits. A seam-4 slice that adds an extractor field also adds its column.

**The thin slice** (ROADMAP, Build order) is groups 1–3: the Page rows, titles, meta descriptions and headings that `040`-min's first Rules read (`title-missing` and `h1-missing`; its response-code Rules read only `urls`). None of them reads Indexability, so group 7 widens with the rest. Groups 4–12 widen the change after `022`-min, whose size and redirect columns group 4 copies.

Rows and units follow `020` D9 and D14: the handler returns frozen row values declared in `spider.store`, and `spider.store.pages` and `spider.store.links` write them with statements built once (`017` D9). Each new writer, and the inlink pass, gets a seam-2 test that forces a replay with `replay_now(writer)` (`017` D7).

## 1. Page rows end to end (slice)

- [ ] 1.1 Drive "HTML response becomes a Page" at seam 3+6. Add the Page handler to `default_hooks()`: a pure function from `020-add-crawl-core`'s `UrlResult` to a Page row. Create `spider.store.pages`, which declares `pages` with `url_id` (references `urls.id`) and `address`, and registers the Page row's writer.
- [ ] 1.2 Drive "Indexes of pages" at seam 6, and add the unique index `pages_address` with the query it serves.
- [ ] 1.3 Drive "Image response is not a Page" at seam 3+6.
- [ ] 1.4 Drive "URL blocked by robots.txt is not a Page" and "URL without a response is not a Page" at seam 3+6. This is a trivial pair: both expect no row.
- [ ] 1.5 Docs: create `docs/page-data.md` covering what a Page is, analysed vs non-analysed Pages and the NULL conventions, with a link from `docs/architecture.md`.
- [ ] 1.6 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Decoding, text and titles (slice)

- [ ] 2.1 Drive "Charset declared in a meta element" at seam 4. Create the Page extractor entry point, registered on `020-add-crawl-core`'s extractor seam, with charset decoding through `020`'s `decode_html` (`spider.crawl.decoding`), never a decoder of its own. Add `title_1`.
- [ ] 2.2 Drive "Whitespace is collapsed before measuring" at seam 4. Add the element-text algorithm and whitespace normalisation, and `title_1_length`.
- [ ] 2.3 Drive "Title in SVG is ignored" at seam 4, and add `title_count` and `title_2`.
- [ ] 2.4 Drive "Second title element" at seam 4, and add `title_2_length`.
- [ ] 2.5 Drive "Missing title" at seam 4.
- [ ] 2.6 Docs: add the decoding order, the text model and the title columns to `docs/page-data.md`.
- [ ] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Meta descriptions and headings (slice)

- [ ] 3.1 Drive "Meta description is normalised" at seam 4, and add `meta_description_1` and `meta_description_1_length`.
- [ ] 3.2 Drive "Multiple meta descriptions" at seam 4, and add `meta_description_count`, `meta_description_2` and `meta_description_2_length`.
- [ ] 3.3 Drive "Meta keywords" at seam 4, and add `meta_keywords_1` and `meta_keywords_1_length`.
- [ ] 3.4 Drive "Heading text includes nested elements" at seam 4, and add the ten `h1_*` and `h2_*` columns.
- [ ] 3.5 Drive "Line break separates heading words" at seam 4 (block breaks).
- [ ] 3.6 Drive "Absent and empty elements differ" at seam 4.
- [ ] 3.7 Docs: add the meta description, meta keywords and heading columns to `docs/page-data.md`.
- [ ] 3.8 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Identity, response, size and redirects

- [ ] 4.1 Drive "Non-ASCII path is decoded for display" and "Punycode host is shown in Unicode" at seam 4. This is a trivial pair: two cases of one display-form function. Add `url_encoded_address`.
- [ ] 4.2 Drive "Path and query of the address" at seam 4, and add `url_path` and `url_query`.
- [ ] 4.3 Drive "Last-Modified is normalised to a timestamp" and "Invalid Last-Modified is NULL" at seam 4. This is a trivial pair: valid and invalid input. Add `last_modified`.
- [ ] 4.4 Drive "Reason phrase falls back to the standard phrase" at seam 4, and add `status`.
- [ ] 4.5 Drive "Error Page keeps response data" at seam 3+6. The handler builds Pages that are not analysed with NULL HTML columns. Add `status_code`.
- [ ] 4.6 Drive "Crawl timestamp repeats fetched_at" at seam 3+6, with the injectable clock. Add `crawl_timestamp`.
- [ ] 4.7 Drive "Compressed Page sizes" at seam 3+6, using `022-add-fetch-policy`'s gzip fixture support with a stored 46-byte blob. Add `size_bytes`, `transferred_bytes` and `content_encoding`.
- [ ] 4.8 Drive "Uncompressed Page sizes" at seam 3+6.
- [ ] 4.9 Drive "Crawl Depth is copied from the crawl engine" at seam 3+6, and add `crawl_depth`.
- [ ] 4.10 Drive "Repeated values equal the urls row" at seam 3+6, and add `content_type` and `response_time_ms`.
- [ ] 4.11 Drive "HTTP redirect with an HTML body" at seam 3+6, and add `redirect_url` and `redirect_type`.
- [ ] 4.12 Drive "HTTP Refresh header is a redirect" at seam 4, from `020`'s `http_refresh` Link.
- [ ] 4.13 Docs: add the identity, response, size and redirect column definitions to `docs/page-data.md`.
- [ ] 4.14 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Cookies

- [ ] 5.1 Drive "Cookie attributes are stored" at seam 4, by parsing `Set-Cookie` headers into cookie records.
- [ ] 5.2 Drive "Cookie count matches the headers" at seam 4, and add `set_cookie_count`.
- [ ] 5.3 Drive "Cookie values are not stored in Page data" at seam 3+6. Create the `cookies` table, keyed by `(url_id, ordinal)` and `WITHOUT ROWID`, and return cookie rows from the handler.
- [ ] 5.4 Drive "Cookies of a redirect are stored" at seam 3+6 (a 302 Page with `Set-Cookie`).
- [ ] 5.5 Docs: add the cookie columns and the no-values rule (with `022`'s `***` redaction) to `docs/page-data.md`.
- [ ] 5.6 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Directives and canonicals

- [ ] 6.1 Drive "Meta robots keeps case but reads directives" at seam 4, using `020-add-crawl-core`'s robots directives parser for the flags. Add `meta_robots`, `meta_robots_noindex` and `meta_robots_nofollow`.
- [ ] 6.2 Drive "X-Robots-Tag is stored with the parser's verdict" at seam 4, and add `x_robots_tag`, `x_robots_tag_noindex` and `x_robots_tag_nofollow`.
- [ ] 6.3 Drive "Meta refresh with a quoted target" at seam 4, using `020`'s discovered `meta_refresh` Link. Add `meta_refresh`, and set `redirect_type` `meta_refresh`.
- [ ] 6.4 Drive "Meta refresh without a target is not a redirect" at seam 4.
- [ ] 6.5 Drive "Relative canonical to another URL" at seam 4, and add `canonical_url`, `canonical_link_element_1`, `canonical_count` and `canonical_relative`.
- [ ] 6.6 Drive "HTML and header canonicals disagree" at seam 4, and add `canonical_link_element_2` and `http_canonical`.
- [ ] 6.7 Drive "Canonical after an image in head is ignored" at seam 4.
- [ ] 6.8 Drive "Base element changes resolution" at seam 4.
- [ ] 6.9 Drive "Pagination from HTML and header" at seam 4 from `020`'s `pagination` Links, and add `rel_next_1`, `rel_prev_1`, `http_rel_next_1` and `http_rel_prev_1`.
- [ ] 6.10 Drive "Mobile alternate and AMP" at seam 4, and add `amphtml_link_element` and `mobile_alternate_link`.
- [ ] 6.11 Docs: add the directive, canonical and pagination columns, and their use of `020`'s parser and Link types, to `docs/page-data.md`.
- [ ] 6.12 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Indexability

- [ ] 7.1 Drive "Plain 200 Page is indexable" at seam 4, and add `indexability` and `indexability_status`.
- [ ] 7.2 Drive "Noindex wins over a canonical" at seam 4.
- [ ] 7.3 Drive "Self-referencing canonical stays indexable" and "Canonical to another URL" at seam 4. This is a trivial pair: the same comparison, with the same URL and with a different one.
- [ ] 7.4 Drive "Server error" at seam 4.
- [ ] 7.5 Drive "Robots.txt beats the status code" at seam 4.
- [ ] 7.6 Drive "Meta refresh redirect is not indexable" at seam 4.
- [ ] 7.7 Drive "HTTP Refresh redirect is not indexable" at seam 4.
- [ ] 7.8 Docs: add the Indexability order and its search-engine rationale to `docs/page-data.md`.
- [ ] 7.9 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Content Area, counts and declared language

- [ ] 8.1 Drive "Default Content Area leaves out navigation" at seam 4. Add the `[content_area]` settings (`include`, `exclude`), fixture A as test data, and `word_count`.
- [ ] 8.2 Drive "Empty exclude list counts everything" at seam 4.
- [ ] 8.3 Drive "Include selector limits the Content Area" at seam 4.
- [ ] 8.4 Drive "Invalid selector stops the Crawl" at seam 1: `settings_invalid` with the key `content_area.exclude`, and 0 requests to the fixture site. Record `content_area` in the Crawl's config.
- [ ] 8.5 Drive "Words with apostrophes, hyphens and dots" at seam 4.
- [ ] 8.6 Drive "Each ideograph and kana is a word" at seam 4.
- [ ] 8.7 Drive "Blocks end sentences" at seam 4, and add `sentence_count`.
- [ ] 8.8 Drive "Text ratio of a small document" at seam 4, and add `text_ratio_pct`.
- [ ] 8.9 Drive "Counts for fixture A" at seam 4, and add `average_words_per_sentence`.
- [ ] 8.10 Drive "Declared language is trimmed, not normalised" at seam 4, and add `declared_language`.
- [ ] 8.11 Docs: add the Content Area settings with examples (including keeping article `<header>` elements), the word and sentence rules, Text Ratio and the declared language column to `docs/page-data.md`.
- [ ] 8.12 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Exact Duplicate hash and structured data

- [ ] 9.1 Drive "Hash of a simple Content Area" at seam 4, and add `content_hash`.
- [ ] 9.2 Drive "Different markup, same text" at seam 4.
- [ ] 9.3 Drive "Composed and decomposed accents hash the same" at seam 4.
- [ ] 9.4 Drive "Empty Content Area has no hash" at seam 4.
- [ ] 9.5 Drive "JSON-LD graph, a broken block and nested Microdata" at seam 4, and add `jsonld_items`, `jsonld_parse_errors`, `microdata_items` and `structured_data_types`.
- [ ] 9.6 Drive "Page without structured data" at seam 4.
- [ ] 9.7 Docs: add the hash definition and the counting rules for JSON-LD and Microdata items and types to `docs/page-data.md`.
- [ ] 9.8 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Link attributes

- [ ] 10.1 Check: the links benchmark, before `links` is declared. If `026` has already run this benchmark and rule (ROADMAP, 026), take its recorded choice instead, and only check that `docs/benchmarks.md` records it and that D4's Storage bullet names it. Otherwise run four layouts at 20,000 Pages, interleaved A B C D D C B A: A, a rowid table with indexes on `target_url_id` and `(type, target_url_id)`; B, `WITHOUT ROWID` with the same indexes; C, `WITHOUT ROWID` with one index on `(target_url_id, type)`; D, narrow rows with a `link_attributes` dictionary keyed by a 64-bit blake2b hash, read through a `links` view. Choose by the rule recorded before the runs: D wins only with at least 30% fewer link bytes, at most 10% fewer Pages/s, and an inlink query p95 under 100 ms while the Crawl writes; otherwise the fastest of A, B and C within 5% wins, and the smaller file on a tie. Done when: the "Links layout" section of `docs/benchmarks.md` records the machine, the runs and the choice, and design D4's Storage bullet names the chosen layout. If D wins, 10.2 also verifies the 8-byte key on insert and clears D's attribute cache on rollback, through a writer hook that this change adds to `017`'s writer.
- [ ] 10.2 Drive "Hyperlink with rel flags" at seam 4. Enrich `020-add-crawl-core`'s `DiscoveredLink` values. Create `spider.store.links` with the Link row's writer, and `links` with `source_url_id`, `ordinal`, `target_url_id`, `type`, `declared_in`, `anchor_text`, `rel` and the three `rel_*` flags, keyed by `(source_url_id, ordinal)`, with `ordinal` and the `rel` tokens taken from `DiscoveredLink` as `020` gives them. Its layout and secondary indexes follow the links benchmark (task 10.1).
- [ ] 10.3 Drive "Image alt attribute absent or empty" at seam 4, and add `element`, `attribute` and `alt_text`.
- [ ] 10.4 Drive "Image-only anchor takes the alt text" at seam 4.
- [ ] 10.5 Drive "Every occurrence is stored" at seam 4.
- [ ] 10.6 Drive "Link positions come from the enclosing element" at seam 4, and add `link_position`.
- [ ] 10.7 Drive "Hreflang and mobile alternate Links" at seam 4, and add `hreflang` and `media`.
- [ ] 10.8 Drive "Links declared in a header" at seam 4.
- [ ] 10.9 Drive "Discovered URLs are the stored Link targets" at seam 3+6. Write Links from analysed Pages, and return the header Links of other responses from the handler.
- [ ] 10.10 Drive "Link types are an enumeration" at seam 6 (`values` on `links.type`).
- [ ] 10.11 Check: the writer's capacity on the chosen `links` layout (`017` D11, moved here from `017`, which records only a 5k-Page smoke run; decided 2026-10-11). Switch `scripts/writer_throughput.py` from its provisional `links` table to the declaration in `spider.store.links`, imported with its key, layout and secondary indexes and never copied into the script, so the check cannot drift from the declared layout; run it at 20,000 Pages on the maintainer's machine, and restate D11's floor (Pages/s, WAL peak, RSS) from that run, in the script and in the "Writer capacity" section of `docs/benchmarks.md`. Done when: the run passes the restated floor, and the section records the machine, the numbers and the layout. If Pages/s falls well below `017`'s 17.2–18.0 on the provisional layout, the work stops and is reported before the floor is lowered.
- [ ] 10.12 Drive "A Page whose Page extractor failed keeps its response data and Links" at seam 3+6, through the Crawl Service with a raising extractor under the Page extractor's name in `default_hooks()`: the handler writes the `pages` row with the extractor's HTML-derived columns NULL, takes the directive verdicts, the canonical and `indexability`'s other inputs from `PageInput` and the prepared record, and writes the `links` rows from `DiscoveredLink` (design D2).
- [ ] 10.13 Docs: add the Link columns, the boundary with `020`'s Link discovery, and what a failed Page extractor leaves (`parse_error` = `extractor_error`) to `docs/page-data.md`.
- [ ] 10.14 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Link counts and Folder Depth

- [ ] 11.1 Drive "Counts for a linked Page" at seam 3+6 on a four-Page fixture site. Add the outlink columns (written with each Page), and the inlink columns with `linking_pages_pct`, computed by the inlink pass, a store function in `spider.store.links` that `default_hooks()` lists before `040`'s pass. The inlink columns get `Derived: ` descriptions, which "Inlink columns are derived" checks at seam 6 in the same slice.
- [ ] 11.2 Drive "Repeated inlinks from one source" at seam 3+6.
- [ ] 11.3 Drive "Inlinks are NULL while the Crawl runs" at seam 3+6.
- [ ] 11.4 Drive "Folder depth" at seam 4, and add `folder_depth`.
- [ ] 11.5 Docs: add the link count definitions, the self-link rule, % of Total (`linking_pages_pct`) and when the post-crawl passes run to `docs/page-data.md`.
- [ ] 11.6 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Later columns, the empty HTML table and cross-platform

- [ ] 12.1 Drive, in one slice, "Schema lists exactly the Page record columns" (seam 6), "Columns of links" (seam 6), "Deferred columns are described with their release" (seam 6) and "Deferred columns are NULL after a completed Crawl" (seam 3+6). All four fail only because the later columns are missing: the 17 of `pages`, and `links.html_source`. Add them as always-NULL columns whose descriptions name their release.
- [ ] 12.2 Drive "HTML is not stored by default" at seam 3+6. Create `page_sources` (`url_id`, an INTEGER PRIMARY KEY referencing `urls.id`, `encoding` and `html`), whose description starts with `Filled from v0.2. `; nothing writes it in v0.1.
- [ ] 12.3 Drive "Non-ASCII title on a Windows console" at seam 1, as a real subprocess on the Windows CI runner with code page 1251.
- [ ] 12.4 Docs: add the later columns and the empty `page_sources` table to `docs/page-data.md`, update the Page data table in `docs/architecture.md` with the stored column names, and check that the column descriptions read well as the Skill's column reference that `080` generates.
- [ ] 12.5 Review: run the code-review skill on group 12's commits and then on the whole change, and refactor with the whole suite green.

## 13. (v0.2) SERP pixel widths

- [ ] 13.1 (v0.2) Drive "Title pixel width" at seam 4. Add the width-table generator script, the generated Liberation Sans table with its OFL notice and the width function, and fill `title_1_width_px`.
- [ ] 13.2 (v0.2) Drive "Wide characters use one em" at seam 4 (fallback widths).
- [ ] 13.3 (v0.2) Drive "Realistic long title" at seam 4.
- [ ] 13.4 (v0.2) Drive "Meta description pixel width" at seam 4, and fill `meta_description_1_width_px`.
- [ ] 13.5 (v0.2) Drive "Widths of second elements" at seam 4, and fill `title_2_width_px` and `meta_description_2_width_px`.
- [ ] 13.6 (v0.2) Docs: add the pixel-width method (source table, font sizes, fallbacks) to `docs/page-data.md`. Drop the `Filled from v0.2. ` prefix from the descriptions of the columns this group fills, and take them out of the list of later columns in the spec.
- [ ] 13.7 (v0.2) Review: run the code-review skill on group 13's commits, then refactor with the whole suite green.

## 14. (v0.2) Syllables, readability and language detection

- [ ] 14.1 (v0.2) Docs: verify each readability formula's coefficients against its cited source (Flesch 1948, Amstad 1978, Szigriszt-Pazos 1993, Kandel & Moles 1958, Douma 1960, Martins et al. 1996, Oborneva 2006), and record the full citations in `docs/page-data.md`. If a coefficient differs, update the spec's formula table and scenario values before 14.2.
- [ ] 14.2 (v0.2) Drive "English score for fixture A" at seam 4, with the English syllable counter, and fill `syllable_count`, `flesch_reading_ease` and `readability`.
- [ ] 14.3 (v0.2) Drive "Syllables per language" at seam 4, with the German and Russian syllable counters.
- [ ] 14.4 (v0.2) Drive "Scores in German, Dutch and Russian" at seam 4, with the Dutch syllable counter and the de, nl and ru formulas.
- [ ] 14.5 (v0.2) Drive "Scores in Spanish, French and Portuguese" at seam 4, with the es, fr and pt syllable counters and formulas.
- [ ] 14.6 (v0.2) Drive "Band of a difficult text" at seam 4.
- [ ] 14.7 (v0.2) Drive "Region subtag and case are ignored" at seam 4.
- [ ] 14.8 (v0.2) Drive "Language without a formula" at seam 4.
- [ ] 14.9 (v0.2) Drive "Detected Russian text" at seam 3+6. Fill `detected_language`, and add `--detect-language` and `[crawl] detect_language`, with `py3langid` imported only when the setting is on.
- [ ] 14.10 (v0.2) Drive "Language detection is off by default" at seam 3+6, a guard that passes once the setting exists: detection runs only when it is on.
- [ ] 14.11 (v0.2) Drive "Detected language is not used for readability" at seam 3+6.
- [ ] 14.12 (v0.2) Docs: add the syllable rules, the readability table and bands, and the detected language column to `docs/page-data.md`. Drop the `Filled from v0.2. ` prefix from the descriptions of the columns this group fills, and take them out of the list of later columns in the spec.
- [ ] 14.13 (v0.2) Review: run the code-review skill on group 14's commits, then refactor with the whole suite green.

## 15. (v0.2) HTTP version and raw HTML storage

- [ ] 15.1 (v0.2) Drive "HTTP version is copied from the origin" at seam 3+6, after `022-add-fetch-policy`'s v0.2 tasks fill `origins.http_version`, and fill `http_version`.
- [ ] 15.2 (v0.2) Drive "The storage decision follows the flags" at seam 4, with the decision function (flags and setting → on or off).
- [ ] 15.3 (v0.2) Drive "The flag stores every Page's HTML" at seam 3+6. Add `--store-html`, store zstd frames with `zstandard`, and record the decision as `store_html`.
- [ ] 15.4 (v0.2) Drive "Stored HTML is byte-identical" at seam 3+6.
- [ ] 15.5 (v0.2) Drive "HTML storage turned off" at seam 1 plus a store-contract read, and add `--no-store-html`.
- [ ] 15.6 (v0.2) Drive "Flag overrides spider.toml" at seam 1 plus a store-contract read, and add `[crawl] store_html`.
- [ ] 15.7 (v0.2) Drive "Encoding of stored HTML" at seam 3+6.
- [ ] 15.8 (v0.2) Docs: add the storage decision, what `resume` keeps, and how to decompress a stored frame to `docs/page-data.md`. Drop the `Filled from v0.2. ` prefix from the descriptions of `page_sources` and `pages.http_version`, and take `http_version` out of the list of later columns in the spec.
- [ ] 15.9 (v0.2) Review: run the code-review skill on group 15's commits, then refactor with the whole suite green.
