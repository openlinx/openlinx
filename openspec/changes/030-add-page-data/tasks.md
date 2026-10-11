> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task is one red → green slice and one commit (see docs/testing.md).
- **Red:** write the failing test for the named scenario at the named seam and watch it fail for the right reason.
- **Green:** write only the code that makes it pass, then run the whole suite.

Seams: 1 CLI, 2 services and store API, 4 pure-logic modules (including the Page extractor), 6 store contract. "Seam 3+6" means crawl the fixture site, then read the documented tables read-only.

There are no schema-first slices. A table or column is added in the slice whose scenario first needs it, through `018`'s declaration helper (`STRICT`, and CHECKs from the declared values and flags), with its description and its `docs/schema.md` entry in the same commit, so the contract test (`015`'s, extended by `018`) is never red between commits. A seam-4 slice that adds an extractor field also adds its column.

Rows and units follow `020` D9 and D14: the handler returns frozen row values declared in `spider.store`, and `spider.store.pages` and `spider.store.links` write them with statements built once (`017` D9). Each new writer, and the inlink pass, gets a seam-2 test that forces a replay with `replay_now(writer)` (`017` D7).

## 1. Page rows end to end

- [ ] 1.1 Drive "HTML response becomes a Page" at seam 3+6. Add the Page handler to `default_hooks()`: a pure function from `020-add-crawl-core`'s `UrlResult` to a Page row. Create `spider.store.pages`, which declares `pages` with `url_id` (references `urls.id`) and `address`, and registers the Page row's writer.
- [ ] 1.2 Drive "Image response is not a Page" at seam 3+6.
- [ ] 1.3 Drive "URL blocked by robots.txt is not a Page" and "URL without a response is not a Page" at seam 3+6. This is a trivial pair: both expect no row.
- [ ] 1.4 Docs: create `docs/page-data.md` covering what a Page is, analysed vs non-analysed Pages and the NULL conventions, with a link from `docs/architecture.md`.
- [ ] 1.5 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Decoding, text and titles

- [ ] 2.1 Drive "Charset declared in a meta element" at seam 4. Create the Page extractor entry point, registered on `020-add-crawl-core`'s extractor seam, with charset decoding. Add `title_1`.
- [ ] 2.2 Drive "Whitespace is collapsed before measuring" at seam 4. Add the element-text algorithm and whitespace normalisation, and `title_1_length`.
- [ ] 2.3 Drive "Title in SVG is ignored" at seam 4, and add `title_count` and `title_2`.
- [ ] 2.4 Drive "Title pixel width" at seam 4. Add the width-table generator script, the generated Liberation Sans table with its OFL notice, the width function, and `title_1_width_px`.
- [ ] 2.5 Drive "Wide characters use one em" at seam 4 (fallback widths).
- [ ] 2.6 Drive "Realistic long title" at seam 4.
- [ ] 2.7 Drive "Second title element" at seam 4, and add `title_2_length` and `title_2_width_px`.
- [ ] 2.8 Drive "Missing title" at seam 4.
- [ ] 2.9 Docs: add the decoding order, the text model, the title columns and the pixel-width method (source table, font sizes, fallbacks) to `docs/page-data.md`.
- [ ] 2.10 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Meta descriptions and headings

- [ ] 3.1 Drive "Meta description is normalised" at seam 4, and add `meta_description_1` and `meta_description_1_length`.
- [ ] 3.2 Drive "Meta description pixel width" at seam 4, and add `meta_description_1_width_px`.
- [ ] 3.3 Drive "Multiple meta descriptions" at seam 4, and add `meta_description_count`, `meta_description_2`, `meta_description_2_length` and `meta_description_2_width_px`.
- [ ] 3.4 Drive "Meta keywords" at seam 4, and add `meta_keywords_1` and `meta_keywords_1_length`.
- [ ] 3.5 Drive "Heading text includes nested elements" at seam 4, and add the ten `h1_*` and `h2_*` columns.
- [ ] 3.6 Drive "Line break separates heading words" at seam 4 (block breaks).
- [ ] 3.7 Drive "Absent and empty elements differ" at seam 4.
- [ ] 3.8 Docs: add the meta description, meta keywords and heading columns to `docs/page-data.md`.
- [ ] 3.9 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Identity, response, size and redirects

- [ ] 4.1 Drive "Non-ASCII path is decoded for display" and "Punycode host is shown in Unicode" at seam 4. This is a trivial pair: two cases of one display-form function. Add `url_encoded_address`.
- [ ] 4.2 Drive "Last-Modified is normalised to a timestamp" and "Invalid Last-Modified is NULL" at seam 4. This is a trivial pair: valid and invalid input. Add `last_modified`.
- [ ] 4.3 Drive "Reason phrase falls back to the standard phrase" at seam 4, and add `status`.
- [ ] 4.4 Drive "Error Page keeps response data" at seam 3+6. The handler builds Pages that are not analysed with NULL HTML columns. Add `status_code`.
- [ ] 4.5 Drive "Crawl timestamp repeats fetched_at" at seam 3+6, with the injectable clock. Add `crawl_timestamp`.
- [ ] 4.6 Drive "HTTP version is copied from the origin" at seam 3+6 (`http_1_1`), and add `http_version`.
- [ ] 4.7 Drive "Compressed Page sizes" at seam 3+6, using `022-add-fetch-policy`'s gzip fixture support with a stored 46-byte blob. Add `size_bytes`, `transferred_bytes` and `content_encoding`.
- [ ] 4.8 Drive "Uncompressed Page sizes" at seam 3+6.
- [ ] 4.9 Drive "Crawl Depth is copied from the crawl engine" at seam 3+6, and add `crawl_depth`.
- [ ] 4.10 Drive "Repeated values equal the urls row" at seam 3+6, and add `content_type` and `response_time_ms`.
- [ ] 4.11 Drive "HTTP redirect with an HTML body" at seam 3+6, and add `redirect_url` and `redirect_type`.
- [ ] 4.12 Docs: add the identity, response, size and redirect column definitions to `docs/page-data.md`.
- [ ] 4.13 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Cookies

- [ ] 5.1 Drive "Cookie attributes are stored" at seam 4, by parsing `Set-Cookie` headers into cookie records.
- [ ] 5.2 Drive "Cookie count matches the headers" at seam 4, and add `set_cookie_count`.
- [ ] 5.3 Drive "Cookie values are not stored in Page data" at seam 3+6. Create the `cookies` table, and return cookie rows from the handler.
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
- [ ] 7.7 Docs: add the Indexability order and its search-engine rationale to `docs/page-data.md`.
- [ ] 7.8 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Content Area and counts

- [ ] 8.1 Drive "Default Content Area leaves out navigation" at seam 4. Add the `[content_area]` settings (`include`, `exclude`), fixture A as test data, and `word_count`.
- [ ] 8.2 Drive "Empty exclude list counts everything" at seam 4.
- [ ] 8.3 Drive "Include selector limits the Content Area" at seam 4.
- [ ] 8.4 Drive "Invalid selector stops the Crawl" at seam 1: `settings_invalid` with the key `content_area.exclude`, and 0 requests to the fixture site. Record `content_area` in the Crawl's config.
- [ ] 8.5 Drive "Words with apostrophes, hyphens and dots" at seam 4.
- [ ] 8.6 Drive "Each ideograph and kana is a word" at seam 4.
- [ ] 8.7 Drive "Blocks end sentences" at seam 4, and add `sentence_count`.
- [ ] 8.8 Drive "Text ratio of a small document" at seam 4, and add `text_ratio_pct`.
- [ ] 8.9 Docs: add the Content Area settings with examples (including keeping article `<header>` elements), the word and sentence rules, and Text Ratio to `docs/page-data.md`.
- [ ] 8.10 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Readability and language

- [ ] 9.1 Docs: verify each readability formula's coefficients against its cited source (Flesch 1948, Amstad 1978, Szigriszt-Pazos 1993, Kandel & Moles 1958, Douma 1960, Martins et al. 1996, Oborneva 2006), and record the full citations in `docs/page-data.md`. If a coefficient differs, update the spec's formula table and scenario values before 9.5.
- [ ] 9.2 Drive "Declared language is trimmed, not normalised" at seam 4, and add `declared_language`.
- [ ] 9.3 Drive "Counts for fixture A" at seam 4, with the English syllable counter. Add `average_words_per_sentence` and `syllable_count`.
- [ ] 9.4 Drive "Syllables per language" at seam 4, with the German and Russian syllable counters.
- [ ] 9.5 Drive "English score for fixture A" at seam 4, and add `flesch_reading_ease` and `readability`.
- [ ] 9.6 Drive "Scores in German, Dutch and Russian" at seam 4, with the Dutch syllable counter and the de, nl and ru formulas.
- [ ] 9.7 Drive "Scores in Spanish, French and Portuguese" at seam 4, with the es, fr and pt syllable counters and formulas.
- [ ] 9.8 Drive "Band of a difficult text" at seam 4.
- [ ] 9.9 Drive "Region subtag and case are ignored" at seam 4.
- [ ] 9.10 Drive "Language without a formula" at seam 4.
- [ ] 9.11 Drive "Language detection is off by default" at seam 3+6, and add `detected_language`.
- [ ] 9.12 Drive "Detected Russian text" at seam 3+6. Add `--detect-language` and `[crawl] detect_language`, with `py3langid` imported only when the setting is on.
- [ ] 9.13 Drive "Detected language is not used for readability" at seam 3+6.
- [ ] 9.14 Docs: add the syllable rules, the readability table and bands, and the declared and detected language columns to `docs/page-data.md`.
- [ ] 9.15 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Exact Duplicate hash and structured data

- [ ] 10.1 Drive "Hash of a simple Content Area" at seam 4, and add `content_hash`.
- [ ] 10.2 Drive "Different markup, same text" at seam 4.
- [ ] 10.3 Drive "Composed and decomposed accents hash the same" at seam 4.
- [ ] 10.4 Drive "Empty Content Area has no hash" at seam 4.
- [ ] 10.5 Drive "JSON-LD graph, a broken block and nested Microdata" at seam 4, and add `jsonld_items`, `jsonld_parse_errors`, `microdata_items` and `structured_data_types`.
- [ ] 10.6 Drive "Page without structured data" at seam 4.
- [ ] 10.7 Docs: add the hash definition and the counting rules for JSON-LD and Microdata items and types to `docs/page-data.md`.
- [ ] 10.8 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Link attributes

- [ ] 11.1 Drive "Hyperlink with rel flags" at seam 4. Enrich `020-add-crawl-core`'s `DiscoveredLink` values. Create `spider.store.links` with the Link row's writer, and `links` with `source_url_id`, `ordinal`, `target_url_id`, `type`, `origin`, `anchor_text`, `rel`, the three `rel_*` flags and `target_is_internal`.
- [ ] 11.2 Drive "Image alt attribute absent or empty" at seam 4, and add `element`, `attribute` and `alt_text`.
- [ ] 11.3 Drive "Image-only anchor takes the alt text" at seam 4.
- [ ] 11.4 Drive "Every occurrence is stored" at seam 4.
- [ ] 11.5 Drive "Navigation Links are outside the Content Area" at seam 4, and add `in_content_area`.
- [ ] 11.6 Drive "Hreflang and mobile alternate Links" at seam 4, and add `hreflang` and `media`.
- [ ] 11.7 Drive "Discovered URLs are the stored Link targets" at seam 3+6. Write Links from analysed Pages, and return the header Links of other responses from the handler.
- [ ] 11.8 Drive "Link types are an enumeration" at seam 6 (`values` on `links.type`).
- [ ] 11.9 Docs: add the Link columns and the boundary with `020`'s Link discovery to `docs/page-data.md`.
- [ ] 11.10 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Link counts and Folder Depth

- [ ] 12.1 Drive "Counts for a linked Page" at seam 3+6 on a four-Page fixture site. Add the outlink columns (written with each Page), and the inlink columns with `linking_pages_pct`, computed by the inlink pass, a store function in `spider.store.links` that `default_hooks()` lists before `040`'s pass.
- [ ] 12.2 Drive "Repeated inlinks from one source" at seam 3+6.
- [ ] 12.3 Drive "Inlinks are NULL while the Crawl runs" at seam 3+6.
- [ ] 12.4 Drive "Folder depth" at seam 4, and add `folder_depth`.
- [ ] 12.5 Docs: add the link count definitions, the self-link rule, % of Total (`linking_pages_pct`) and when the post-crawl passes run to `docs/page-data.md`.
- [ ] 12.6 Review: run the code-review skill on group 12's commits, then refactor with the whole suite green.

## 13. Raw HTML storage

- [ ] 13.1 Drive "The automatic decision follows the URL limit" at seam 4, with the decision function (flags, setting, `max_urls` → on or off).
- [ ] 13.2 Drive "Default limit stores HTML automatically" at seam 3+6. Create `page_sources`, store zstd frames with `zstandard`, and record the decision as `store_html`.
- [ ] 13.3 Drive "Stored HTML is byte-identical" at seam 3+6.
- [ ] 13.4 Drive "Large limit turns automatic storage off" at seam 3+6.
- [ ] 13.5 Drive "HTML storage turned off" at seam 1 plus a store-contract read, and add `--store-html` and `--no-store-html`.
- [ ] 13.6 Drive "Flag overrides spider.toml" at seam 1 plus a store-contract read, and add `[crawl] store_html`.
- [ ] 13.7 Drive "Encoding of stored HTML" at seam 3+6.
- [ ] 13.8 Docs: add the storage decision, what `resume` keeps, and how to decompress a stored frame to `docs/page-data.md`.
- [ ] 13.9 Review: run the code-review skill on group 13's commits, then refactor with the whole suite green.

## 14. Full column set and cross-platform

- [ ] 14.1 Drive, in one slice, "Schema lists exactly the Page record columns" (seam 6), "Deferred columns are described with their release" (seam 6) and "Deferred columns are NULL after a completed Crawl" (seam 3+6). All three fail only because the eight deferred columns are missing. Add them as always-NULL columns whose descriptions name their release.
- [ ] 14.2 Drive "Non-ASCII title on a Windows console" at seam 1, as a real subprocess on the Windows CI runner with code page 1251.
- [ ] 14.3 Docs: update the Page data table in `docs/architecture.md` with the stored column names, and check that the column descriptions read well as the Skill's column reference that `080` generates.
- [ ] 14.4 Review: run the code-review skill on group 14's commits and then on the whole change, and refactor with the whole suite green.
