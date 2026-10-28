Each task is one red → green slice and one commit (see docs/testing.md).
- **Red:** write the failing test for the named scenario at the named seam and watch it fail for the right reason.
- **Green:** write only the code that makes it pass, then run the whole suite.

Seams: 1 CLI, 2 services and store API, 4 pure-logic modules (including the Page extractor), 6 store contract. "Seam 3+6" means crawl the fixture site, then read the documented tables read-only.

There are no schema-first slices. A table or column is added in the slice whose scenario first needs it, through `018`'s `public_table()` (`STRICT`, and CHECKs from the declared values and flags), with its description and its `docs/schema.md` entry in the same commit, so the contract test (`015`'s, extended by `018`) is never red between commits. A seam-4 slice that adds an extractor field also adds its column.

**The thin slice** (ROADMAP, Build order) is groups 1–3: the Page rows, titles, meta descriptions and headings that `040`-min's first Rules read (`title-missing` and `h1-missing`; its response-code Rules read only `urls`). None of them reads Indexability. The groups after it run in the order 4, 5, 8, 6, 7, 9, 10, 11, 12, 4b, with task 4.3 before group 6 and reviewed with it, so Indexability, which `040`'s `indexable_pages` reads, comes as early as its inputs allow. Group 4b copies `022`-min's size and redirect columns and waits for it.

Rows and units follow `020` D9 and D14: one handler per table (`pages`, `links` and `cookies`), each a pure function of the URL's result that returns frozen row values declared in `spider.store.page_records`, which loads no sqlalchemy, all or none, and names the store function that writes them. The tables are declared in `spider.store.schema`, and `spider.store.pages` and `spider.store.links` hold the writers, with statements built once (`017` D9). The Page extractor (`spider.extract.page_data`, which imports only `spider.crawl.pages.preparation` and the pure text helpers of `spider.extract`, so `026`'s workers never load sqlalchemy), the three handlers, the depth pass and the inlink pass are listed in `spider.services.hooks.default_hooks()`, `020`'s composition root. Each new writer, and the inlink pass, gets a seam-2 test that forces a replay with `replay_now(writer)` (`017` D7).

A seam-4 slice of the Page extractor runs `020`'s `prepare_page` over the HTML as bytes, with the Page extractor in its `PageSettings`, then the Page handler over the resulting `UrlResult`, and asserts the Page row: one pure test covers the decoding, the extractor and the handler's mapping to the column.

## 1. Page rows end to end (slice)

- [x] 1.1 Drive "HTML response becomes a Page" at seam 3+6. Declare `pages` in `spider.store.schema` with `url_id` (references `urls.id`) and `address`. Add the Page row to `spider.store.page_records` and its writer to `spider.store.pages`, and list the Page handler (`spider.extract.page_handler`, a pure function from `020-add-crawl-core`'s `UrlResult` to a Page row) and the writer in `spider.services.hooks.default_hooks()`.
- [x] 1.2 Drive "Non-ASCII path is decoded for display" and "Punycode host is shown in Unicode" at seam 4 (moved from group 4). This is a trivial pair: two cases of one display-form function. Add `url_encoded_address`, and write `address` in the display form.
- [x] 1.3 Drive "Indexes of pages" at seam 6, and add the unique index `pages_address` with the query it serves.
- [x] 1.4 Drive "Image response is not a Page" at seam 3+6.
- [x] 1.5 Drive "URL blocked by robots.txt is not a Page" and "URL without a response is not a Page" at seam 4, on the `UrlResult` that `020` records for each: `skipped` with `blocked_by_robots_txt`, and `error` with a `fetch_error`. This is a trivial pair: both expect no row. `020`'s task 10.5 and `022`'s timeout scenario pin those records end to end.
- [x] 1.6 Drive "External HTML response is not a Page" at seam 3+6, through `020`'s DNS resolver hook. The Page handler reads `is_internal` and `in_scope` from the `UrlResult`.
- [x] 1.7 Docs: create `docs/page-data.md` covering what a Page is, analysed vs non-analysed Pages, the NULL conventions and the two address forms, with a link from `docs/architecture.md`.
- [x] 1.8 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green. The review amended the Address columns, and drives "Invisible and control characters stay encoded" at seam 4.

## 2. Decoding, text and titles (slice)

- [x] 2.1 Drive "Charset declared in a meta element" at seam 4. Create the Page extractor in `spider.extract.page_data`, listed in `spider.services.hooks.default_hooks()`: a pure, module-level function of page preparation's tree and `PageInput` to a frozen msgspec Struct, which the Page handler reads under the extractor's name. It reads the tree that page preparation built with `020`'s `decode_html` (`spider.crawl.pages.decoding`) and decodes nothing itself. Add `title_1`.
- [x] 2.2 Drive "Whitespace is collapsed before measuring" at seam 4. Add whitespace normalisation (ASCII whitespace only) and `title_1_length`.
- [x] 2.3 Drive "Title in SVG is ignored" at seam 4, and add `title_count` and `title_2`.
- [x] 2.4 Drive "Second title element" at seam 4, and add `title_2_length`.
- [x] 2.5 Drive "Missing title" at seam 4.
- [x] 2.6 Docs: add the decoding order, the text model and the title columns to `docs/page-data.md`.
- [x] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green. The review drives "Title in noscript is ignored" at seam 4.

## 3. Meta descriptions and headings (slice)

- [x] 3.1 Drive "Meta description is normalised" at seam 4, and add `meta_description_1` and `meta_description_1_length`.
- [x] 3.2 Drive "Multiple meta descriptions" at seam 4, and add `meta_description_count`, `meta_description_2` and `meta_description_2_length`.
- [x] 3.3 Drive "Meta keywords" at seam 4, and add `meta_keywords_1` and `meta_keywords_1_length`.
- [x] 3.4 Drive "Heading text includes nested elements" at seam 4. Add the element-text algorithm (text nodes in document order, without the contents of the skipped elements) and the ten `h1_*` and `h2_*` columns.
- [x] 3.5 Drive "Line break separates heading words" at seam 4 (block breaks at `br` and at block-level elements).
- [x] 3.6 Drive "Absent and empty elements differ" at seam 4.
- [x] 3.7 Docs: add the meta description, meta keywords and heading columns to `docs/page-data.md`.
- [x] 3.8 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.
- [x] 3.9 Review fixes of group 3, each test-first with its cause: headings read the text of their first two elements only and count the rest (nested headings made the text walk quadratic); the never-raises property builds headings, breaks, blocks, `noscript` and meta descriptions, and a deep-nesting test runs the walker; a test pins every element of the walker's skip list; the ancestor rule becomes one `:not(svg *, math *, noscript *)` query if that is simpler and not slower.

## 4. Identity and response

Task 4.0 is task 12.4, moved here; 4.6, 4.7 and 4.10 moved to group 4b, and 4.11 to group 6 as task 6.13.

- [x] 4.0 Drive "Title in head noscript is ignored" at seam 4, a `test:` guard over the tree page preparation gives: red by page preparation parsing with scripting off.
- [x] 4.1 Drive "Path and query of the address" at seam 4, and add `url_path` and `url_query`.
- [x] 4.2 Drive "Last-Modified is normalised to a timestamp" and "Invalid Last-Modified is NULL" at seam 4. This is a trivial pair: valid and invalid input. Add `last_modified`.
- [x] 4.4 Drive "Error Page keeps response data" at seam 3+6, and add `status_code`. The handler already builds a Page that is not analysed with NULL HTML columns.
- [x] 4.5 Drive "Crawl timestamp repeats fetched_at" at seam 3+6, with the injectable clock. Add `crawl_timestamp`.
- [x] 4.8 Drive "Crawl Depth is copied from the crawl engine" at seam 3+6, and add `crawl_depth`, copied from the URL's result; the depth pass (task 11.7) corrects it after the Crawl.
- [x] 4.9 Drive "Repeated values equal the urls row" at seam 3+6 over the columns that exist, and add `content_type` and `response_time_ms`. Task 4.6 extends the same test to the size columns.
- [x] 4.12 Docs: add the identity and response concepts to `docs/page-data.md` (the address forms with their path and query, the timestamps, the values that repeat `urls`), as cross-column concepts only, since each column's description is its one definition; trim the per-column bullets of groups 1–3 to the same rule.
- [x] 4.13 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.
- [x] 4.16 Fix the findings of the review of group 4: read `pages.crawl_depth` from `urls` in the Page's unit, pin that the first `Last-Modified` header wins and a heading count above 2, and settle the date edge cases, the address without a path, and the docs' history and repeated facts.
- [ ] 4.3 Drive "Reason phrase falls back to the standard phrase" at seam 4, and add `status`, from the reason phrase of the URL's response.

## 5. Cookies

- [x] 5.1 Drive "Cookie attributes are stored" at seam 4, by parsing `Set-Cookie` headers into cookie records.
- [x] 5.2 Drive "Cookie count matches the headers" at seam 4, and add `set_cookie_count`.
- [x] 5.3 Drive "Cookie values are not stored in Page data" at seam 3+6. Create the `cookies` table, keyed by `(url_id, ordinal)` and `WITHOUT ROWID`, and the `cookies` handler with its writer. The test reads every table this change declares in `spider.store.schema`, so `links` and `page_sources` join it once they exist.
- [x] 5.4 Drive "Cookies of a redirect are stored" at seam 3+6 (a 302 Page with `Set-Cookie`).
- [x] 5.5 Docs: add the cookie concepts and the rule that this change's tables store no cookie value to `docs/page-data.md`.
- [x] 5.6 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.
- [x] 5.7 Fix the findings of the review of group 5, before group 8's first slice: a `Domain` that is no host name or IP address, and a `Path` that does not start with `/`, are NULL, so a folded header stores no value; a Max-Age beyond 64 bits is clamped; real repeated attributes and a lowercase name from an HTTP/1.1 proxy in the tests; the cookie column test compares sets; and the in-flight depth test is sequenced on a request with the fixture site's `after`, not on delays.

## 6. Directives and canonicals

Every task of this group but 6.0 reads the URL's result. Task 6.13 is task 4.11, moved here, and comes before 6.3.

- [ ] 6.0 Add `tests/support/headers.py`: real `Set-Cookie` and `Last-Modified` headers, each with the stack that sends it (PHP, Django, Rails, Express, nginx and a CDN). The seam-4 cookie and Last-Modified tests and one hypothesis property draw from it. Pin that `SameSite=Lax; SameSite=Foo` gives `same_site` NULL, as an unknown SameSite is not ignored.
- [ ] 6.1 Drive "Meta robots keeps case but reads directives" at seam 4, from the robots directives of the URL's result, which `020-add-crawl-core`'s parser gives. Add `meta_robots`, `meta_robots_noindex` and `meta_robots_nofollow`.
- [ ] 6.2 Drive "X-Robots-Tag is stored with the parser's verdict" and "X-Robots-Tag is kept when page preparation fails" at seam 4, a trivial pair: the same columns from the URL's result, for an analysed Page and for one whose preparation failed. Add `x_robots_tag`, `x_robots_tag_noindex` and `x_robots_tag_nofollow`.
- [ ] 6.13 Drive "HTTP Refresh header is a redirect" at seam 4, from `020`'s `http_refresh` Link, and add `redirect_url` and `redirect_type` with all its values.
- [ ] 6.3 Drive "Meta refresh with a quoted target" at seam 4: `meta_refresh` from the Page extractor, and `redirect_type` `meta_refresh` with `redirect_url` from `020`'s discovered `meta_refresh` Link. Add `meta_refresh`.
- [ ] 6.4 Drive "Meta refresh without a target is not a redirect" at seam 4.
- [ ] 6.5 Drive "Relative canonical to another URL" at seam 4, from the `canonical` Links of the URL's result that are in `<head>` or in a header, and add `canonical_url`, `canonical_link_element_1`, `canonical_count` and `canonical_relative`.
- [ ] 6.6 Drive "HTML and header canonicals disagree" at seam 4, and add `canonical_link_element_2` and `http_canonical`.
- [ ] 6.7 Drive "Canonical after an image in head is ignored" at seam 4.
- [ ] 6.8 Drive "Base element changes resolution" at seam 4.
- [ ] 6.9 Drive "Pagination from HTML and header" at seam 4 from `020`'s `pagination` Links, and add `rel_next_1`, `rel_prev_1`, `http_rel_next_1` and `http_rel_prev_1`.
- [ ] 6.10 Drive "Mobile alternate and AMP" at seam 4, and add `amphtml_link_element` and `mobile_alternate_link`.
- [ ] 6.11 Docs: add the reason phrase, the directive, canonical and pagination columns, and their use of `020`'s parser and Link types, to `docs/page-data.md`.
- [ ] 6.12 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Indexability

- [ ] 7.1 Drive "Plain 200 Page is indexable" at seam 4, and add `indexability` and `indexability_status`.
- [ ] 7.2 Drive "Noindex wins over a canonical" at seam 4.
- [ ] 7.3 Drive "Self-referencing canonical stays indexable" and "Canonical to another URL" at seam 4. This is a trivial pair: the same comparison, with the same URL and with a different one.
- [ ] 7.4 Drive "Server error" at seam 4, with a `status_code` keyword of `page_row`.
- [ ] 7.5 Drive "Robots.txt beats the status code" at seam 4, with a `blocked_by_robots_txt` keyword of `page_row`.
- [ ] 7.6 Drive "Meta refresh redirect is not indexable" at seam 4.
- [ ] 7.7 Drive "HTTP Refresh redirect is not indexable" at seam 4.
- [ ] 7.8 Docs: add the Indexability order and its search-engine rationale to `docs/page-data.md`.
- [ ] 7.9 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Content Area, counts and declared language

- [x] 8.1 Drive "Default Content Area leaves out navigation" at seam 4. Add the `[content_area]` settings (`include`, `exclude`), the Page extractor's config, which `default_hooks(settings)` resolves from the Crawl's settings; fixture A as test data; and `word_count`. The Content Area, words and sentences live in `spider.extract.content`, over one text walk in `spider.extract.text` that yields blocks. The `[content_area]` table is registered beside `[crawl]`, its selectors validated by compiling them with the parser, and `CrawlPlan.loaded` brings the loaded settings to `default_hooks`, which `spider.cli.crawl` passes; without settings, `default_hooks()` gives the default Content Area. The new columns follow `h2_count`, in the spec's order.
- [x] 8.2 Drive "Empty exclude list counts everything" at seam 4.
- [x] 8.3 Drive "Include selector limits the Content Area" at seam 4.
- [ ] 8.4 Drive "Invalid selector stops the Crawl" at seam 1: `settings_invalid` with the key `content_area.exclude`, and 0 requests to the fixture site. Record `content_area` in the Crawl's config. Assert at seam 1 that a Crawl with its own `[content_area]` records it under `content_area`, and that fixture A crawled with `exclude = []` in `spider.toml` stores `word_count` 13.
- [ ] 8.5 Drive "Words with apostrophes, hyphens and dots" at seam 4. Pin with tests named after no scenario, on real page text: a Devanagari word with its marks is one word, `snake_case` is two, and `カード` is three. Measure the word count on a real 1 MB Japanese page and a real 1 MB English page; each stays under about 50 ms.
- [ ] 8.6 Drive "Each ideograph and kana is a word" at seam 4. Han, Hiragana and Katakana come from a range table of Scripts.txt, compiled into the tokenizer's regular expression. The table names its Unicode version, and a test pins it to `unicodedata.unidata_version`.
- [ ] 8.7 Drive "Blocks end sentences" at seam 4, and add `sentence_count`.
- [ ] 8.8 Drive "Text ratio of a small document" at seam 4, and add `text_ratio_pct`, over `PageInput.length`. It is NULL for an empty decoded document, and rounded half up from its exact quotient.
- [ ] 8.9 Drive "Counts for fixture A" at seam 4, and add `average_words_per_sentence`.
- [ ] 8.10 Drive "Declared language is trimmed, not normalised" at seam 4, and add `declared_language`. A `lang` attribute without a value gives the empty string.
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
- [ ] 10.2 Drive "Hyperlink with rel flags" at seam 4. Enrich `020-add-crawl-core`'s `DiscoveredLink` values in the Link extractor, `PAGE_LINKS` in `spider.extract`, beside the Page extractor. Create `spider.store.links` with the Link row's writer, the `links` handler, and `links` with `source_url_id`, `ordinal`, `target_url_id`, `type`, `declared_in`, `anchor_text`, `rel` and the three `rel_*` flags, keyed by `(source_url_id, ordinal)`, with `ordinal` and the `rel` tokens taken from `DiscoveredLink` as `020` gives them. Its layout and secondary indexes follow the links benchmark (task 10.1).
- [ ] 10.3 Drive "Image alt attribute absent or empty" at seam 4, and add `element`, `attribute` and `alt_text`.
- [ ] 10.4 Drive "Image-only anchor takes the alt text" at seam 4.
- [ ] 10.5 Drive "Every occurrence is stored" at seam 4.
- [ ] 10.6 Drive "Link positions come from the enclosing element" at seam 4, and add `link_position`.
- [ ] 10.7 Drive "Hreflang and mobile alternate Links" at seam 4, and add `hreflang` and `media`.
- [ ] 10.8 Drive "Links declared in a header" at seam 4.
- [ ] 10.9 Drive "Discovered URLs are the stored Link targets" at seam 3+6. Write the Links of the URL's result: those of analysed Pages, and the header Links of other responses.
- [ ] 10.10 Drive "Link types are an enumeration" at seam 6 (`values` on `links.type`).
- [ ] 10.11 Check: the writer's capacity on the chosen `links` layout (`017` D11, moved here from `017`, which records only a 5k-Page smoke run; decided 2026-10-11). Switch `scripts/writer_throughput.py` from its provisional `links` table to the declaration in `spider.store.links`, imported with its key, layout and secondary indexes and never copied into the script, so the check cannot drift from the declared layout; run it at 20,000 Pages on the maintainer's machine, and restate D11's floor (Pages/s, WAL peak, RSS) from that run, in the script and in the "Writer capacity" section of `docs/benchmarks.md`. Done when: the run passes the restated floor, and the section records the machine, the numbers and the layout. If Pages/s falls well below `017`'s 17.2–18.0 on the provisional layout, the work stops and is reported before the floor is lowered.
- [ ] 10.12 Drive "A Page whose Page extractor failed keeps its response data and Links" at seam 3+6, through the Crawl Service with raising extractors under the names of the Page extractor and the Link extractor in `default_hooks()` in `spider.services.hooks`, the composition root: the handler writes the `pages` row with the extractor's HTML-derived columns NULL, takes the directive verdicts, the canonical and `indexability`'s other inputs from the URL's result, and writes the `links` rows from its `DiscoveredLink` values (design D2).
- [ ] 10.13 Docs: add the Link columns, the boundary with `020`'s Link discovery, and what a failed Page extractor leaves (`parse_error` = `extractor_error`) to `docs/page-data.md`.
- [ ] 10.14 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Link counts and Folder Depth

- [ ] 11.1 Drive "Counts for a linked Page" at seam 3+6 on a four-Page fixture site. Add the outlink columns (written with each Page), and the inlink columns with `linking_pages_pct`, computed by the inlink pass, a store function in `spider.store.links` that `default_hooks()` in `spider.services.hooks`, the composition root, lists before `040`'s pass. The inlink columns get `Derived: ` descriptions, which "Inlink columns are derived" checks at seam 6 in the same slice.
- [ ] 11.2 Drive "Repeated inlinks from one source" at seam 3+6.
- [ ] 11.3 Drive "Inlinks are NULL while the Crawl runs" at seam 3+6.
- [ ] 11.4 Drive "Folder depth" at seam 4, and add `folder_depth`.
- [ ] 11.7 Drive "Crawl Depth is the shortest path over followed Links" at seam 2, and add `links.followed`, `020`'s `DiscoveredLink.requests_target`, whose description says it is 1 when the Crawl requests the target through the Link, a Resource included. The depth pass, a store function in `spider.store.links` that `default_hooks()` lists before the inlink pass, is set-based (design D18): it updates `urls.crawl_depth` and `pages.crawl_depth` in units, writes the same rows when run twice (`replay_now`), and runs again after `resume`. It settles the description of `pages.crawl_depth`, which says the column equals `urls.crawl_depth`, and whether ADR-0005 rule 12 (`Derived: `) applies to it.
- [ ] 11.5 Docs: add the link count definitions, the self-link rule, % of Total (`linking_pages_pct`), the depth pass, that a URL skipped at `--max-depth` has `links` rows but no `pages` row, and when the post-crawl passes run to `docs/page-data.md`.
- [ ] 11.6 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Later columns, the empty HTML table and cross-platform

Task 12.4 moved to group 4 as task 4.0.

- [ ] 12.1 Drive, in one slice, "Schema lists exactly the Page record columns" (seam 6), "Columns of links" (seam 6), "Deferred columns are described with their release" (seam 6) and "Deferred columns are NULL after a completed Crawl" (seam 3+6). All four fail only because the later columns are missing: the 17 of `pages`, and `links.html_source`. Add them as always-NULL columns whose descriptions name their release.
- [ ] 12.2 Drive "HTML is not stored by default" at seam 3+6. Create `page_sources` (`url_id`, an INTEGER PRIMARY KEY referencing `urls.id`, `encoding` and `html`), whose description starts with `Filled from v0.2. `; nothing writes it in v0.1. Extend the test of "Cookie values are not stored in Page data" to decompress `page_sources.html`, since it scans only text values.
- [ ] 12.3 Drive "Non-ASCII title on a Windows console" at seam 1, as a real subprocess on the Windows CI runner with code page 1251.
- [ ] 12.5 Docs: add the later columns and the empty `page_sources` table to `docs/page-data.md`, update the Page data table in `docs/architecture.md` with the stored column names, and check that the column descriptions read well as the Skill's column reference that `080` generates.
- [ ] 12.6 Review: run the code-review skill on group 12's commits and then on the whole change, and refactor with the whole suite green. Before the change is archived, give D5 to D12 and D15 an `**In short:**` opener, and reduce each Risks entry of tests named after no scenario to the test's name and the failure class it guards.

## 4b. Sizes and HTTP redirects (after 022-min)

- [ ] 4.6 Drive "Compressed Page sizes" at seam 3+6, using `022-add-fetch-policy`'s gzip fixture support with a stored 46-byte blob. Add `size_bytes`, `transferred_bytes` and `content_encoding`, and extend the test of "Repeated values equal the urls row" to them.
- [ ] 4.7 Drive "Uncompressed Page sizes" at seam 3+6.
- [ ] 4.10 Drive "HTTP redirect with an HTML body" at seam 3+6: `redirect_type` `http_redirect`, and `redirect_url` from `022`'s `urls.redirect_url_id`.
- [ ] 4.17 Drive "A redirect adds no Crawl Depth" at seam 2: the depth pass walks `urls.redirect_url_id` as an edge of weight 0.
- [ ] 4.14 Docs: add the size and HTTP redirect concepts, and the redirect's weight in the depth pass to `docs/page-data.md`.
- [ ] 4.15 Review: run the code-review skill on group 4b's commits, then refactor with the whole suite green.

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
