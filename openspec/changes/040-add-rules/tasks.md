> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task is one red → green slice and one commit (see docs/testing.md).
- **Red:** write the failing test for the named scenario at the named seam and watch it fail for the right reason.
- **Green:** write only the code that makes it pass, then run the whole suite.

Seams: 1 CLI, 2 services and store API, 4 pure-logic modules, 6 store contract. "Seam 3+6" means crawl the fixture site, then read the documented tables read-only.

- **Tables and columns.** There are no schema-first slices. A table or column is added in the slice whose scenario first needs it, with its `docs/schema.md` entry in the same commit, so `015-add-crawl-store`'s contract test is never red between commits.
- **Rules.** Each Rule is registered, with its final `description`, `why_it_matters` and `how_to_fix` texts, in the slice that first needs it.

## 1. Rule model and the rules Command

- [ ] 1.1 Drive "First Rule in the list" and "Every Rule has its guidance" at seam 1. This is a trivial pair: both fail until the registry and the Command exist. Add the Rule model, the registry, `internal-4xx` with its guidance texts, and `spider rules list` on `010`'s output contract.
- [ ] 1.2 Drive "Show a Rule with thresholds" at seam 1. Register `title-too-long` with its thresholds and texts, and add `spider rules show <id>`.
- [ ] 1.3 Drive "Rule without thresholds" at seam 1, and register `title-missing`.
- [ ] 1.4 Drive "Unknown Rule id" at seam 1: `rule_not_found`, exit code 4, and a hint naming `spider rules list`.
- [ ] 1.5 Drive "Windows console output" at seam 1, as a real subprocess on the Windows CI runner with code page 1251.
- [ ] 1.6 Docs: create `docs/rules.md` covering the Rule model, what Issue Type and Priority mean, the Issue-type principle with `http-url` as Warning/High (design D3), category and id naming (D12) and how to read `spider rules` output.
- [ ] 1.7 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Configuration in spider.toml

- [ ] 2.1 Drive "Override shown by the rules Command" at seam 1, and add `[rules.<id>]` thresholds to `010`'s settings model.
- [ ] 2.2 Drive "Disabled Rule is listed" at seam 1 (`enabled = false`), and register `url-parameters`.
- [ ] 2.3 Drive "Misspelt Rule id" at seam 1: `settings_invalid` with a dotted key and a closest-id hint.
- [ ] 2.4 Drive "Unknown key" at seam 1, and register `h2-missing`.
- [ ] 2.5 Drive "Negative threshold" at seam 1. `spider crawl` exits 3, and the fixture site receives 0 requests. Register `low-word-count`.
- [ ] 2.6 Docs: add `[rules.<id>]` examples to `docs/rules.md`: raising a limit, disabling a Rule, and the error for a misspelt id.
- [ ] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Evaluation during the Crawl and stored Issues

- [ ] 3.1 Drive "Crawl records the thresholds it used" at seam 3+6. Create the `rules` table and write the configuration snapshot when a Crawl starts.
- [ ] 3.2 Drive "Categories are an enumeration" at seam 6 (`values` on `rules.category`).
- [ ] 3.3 Drive "Missing title" at seam 4, through the Rule evaluation entry point.
- [ ] 3.4 Drive "Empty title counts as missing" at seam 4.
- [ ] 3.5 Drive "Non-analysed Pages are skipped by Page Rules" at seam 4.
- [ ] 3.6 Drive "Issue row counts its Affected URLs" at seam 3+6. Create `issues` and `affected_urls`, and evaluate Page Rules in `020-add-crawl-core`'s per-response hook, inside the URL's writer unit.
- [ ] 3.7 Drive "Issue Types are an enumeration" at seam 6 (`values` on `issues.issue_type`).
- [ ] 3.8 Drive "Issue visible before the Crawl ends" at seam 3+6, with a fixture page that delays its response by 5 s.
- [ ] 3.9 Drive "Missing H2" at seam 4.
- [ ] 3.10 Drive "Disabled Rule produces no Issue" at seam 3+6.
- [ ] 3.11 Docs: add the `rules`, `issues` and `affected_urls` tables, with a sample query for each, to `docs/rules.md`.
- [ ] 3.12 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Title Rules and the post-crawl passes

- [ ] 4.1 Drive "Title too long by characters" at seam 4.
- [ ] 4.2 Drive "Title too long by pixels" at seam 4.
- [ ] 4.3 Drive "Title at both limits" at seam 4.
- [ ] 4.4 Drive "Raised title limit" at seam 4, passing effective thresholds to the evaluation entry point.
- [ ] 4.5 Drive "Detail is stored as JSON" at seam 3+6, with the fixture page `/rules/long-title`.
- [ ] 4.6 Drive "Title too short" and "Title at the minimum" at seam 4. This is a trivial pair: one boundary. Register `title-too-short`.
- [ ] 4.7 Drive "Multiple titles" at seam 4, and register `title-multiple`.
- [ ] 4.8 Drive "Rule that did not fire has no Issue" at seam 3+6.
- [ ] 4.9 Drive "Title equals H1" and "Comparison with H1 is case-sensitive" at seam 4. This is a trivial pair: the same comparison. Register `title-same-as-h1`.
- [ ] 4.10 Drive "Duplicate titles among Indexable Pages" at seam 4, with one grouping function for Indexable Pages. Register `title-duplicate`.
- [ ] 4.11 Drive "Non-indexable Pages are not compared" at seam 4.
- [ ] 4.12 Drive "Duplicates found by the post-crawl passes" at seam 3+6. Run the `post_crawl` Rules in `020-add-crawl-core`'s post-crawl passes hook, after `030`'s link counts.
- [ ] 4.13 Drive "Post-crawl Rules wait for the passes" at seam 3+6.
- [ ] 4.14 Drive "A second pass does not duplicate rows" at seam 2. The passes replace the rows of `post_crawl` Rules and recount `issues` in one writer unit.
- [ ] 4.15 Docs: add the 6 title Rules (id, type, priority, condition, detail, guidance) to the catalogue in `docs/rules.md`.
- [ ] 4.16 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Meta description and heading Rules

- [ ] 5.1 Drive "Missing meta description" at seam 4, and register `meta-description-missing`.
- [ ] 5.2 Drive "Meta description too long" and "Meta description at both limits" at seam 4. This is a trivial pair: one boundary. Register `meta-description-too-long`.
- [ ] 5.3 Drive "Meta description too short" at seam 4, and register `meta-description-too-short`.
- [ ] 5.4 Drive "Multiple meta descriptions" at seam 4, and register `meta-description-multiple`.
- [ ] 5.5 Drive "Duplicate meta descriptions" at seam 4, and register `meta-description-duplicate`.
- [ ] 5.6 Drive "Missing H1" at seam 4, and register `h1-missing`.
- [ ] 5.7 Drive "Multiple H1" at seam 4, and register `h1-multiple`.
- [ ] 5.8 Drive "H1 too long" and "H1 at the limit" at seam 4. This is a trivial pair: one boundary. Register `h1-too-long`.
- [ ] 5.9 Drive "Duplicate H1" at seam 4, and register `h1-duplicate`.
- [ ] 5.10 Docs: add the 5 meta description Rules and the 5 heading Rules to the catalogue in `docs/rules.md`.
- [ ] 5.11 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Response code and security Rules

- [ ] 6.1 Drive "Client error" at seam 4, over `urls` rows.
- [ ] 6.2 Drive "External URLs are not Internal URLs" at seam 4.
- [ ] 6.3 Drive "Client error recorded during the Crawl" at seam 3+6, by evaluating URL Rules in the per-response hook for every recorded URL.
- [ ] 6.4 Drive "Server error" at seam 4, and register `internal-5xx`.
- [ ] 6.5 Drive "No response" at seam 4, and register `internal-no-response`.
- [ ] 6.6 Drive "Blocked even when crawled anyway" at seam 4, and register `internal-blocked-by-robots-txt`.
- [ ] 6.7 Drive "Internal redirect" at seam 4, and register `internal-3xx`.
- [ ] 6.8 Drive "Two-hop chain" and "One hop is not a chain" at seam 4. This is a trivial pair: the walk along `redirect_url_id` and its boundary. Register `redirect-chain`.
- [ ] 6.9 Drive "Loop" at seam 4, using `redirect_loop`. Register `redirect-loop`.
- [ ] 6.10 Drive "Content served over HTTP" and "HTTP URL that redirects to HTTPS" at seam 4. This is a trivial pair. Register `http-url` as Warning/High.
- [ ] 6.11 Docs: add the 7 response code Rules and `http-url` to the catalogue in `docs/rules.md`.
- [ ] 6.12 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Canonical and directive Rules

- [ ] 7.1 Drive "Missing canonical" and "Noindex Page needs no canonical" at seam 4. This is a trivial pair. Register `canonical-missing`.
- [ ] 7.2 Drive "Canonicalised Page" at seam 4, and register `canonicalised`.
- [ ] 7.3 Drive "Relative canonical" at seam 4, and register `canonical-relative`.
- [ ] 7.4 Drive "Conflicting canonicals" and "Agreeing canonicals" at seam 4. This is a trivial pair. Register `canonical-conflicting`.
- [ ] 7.5 Drive "Canonical to a redirect" at seam 4, with the target-Indexability function (design D13). Register `canonical-to-non-indexable`.
- [ ] 7.6 Drive "Canonical to a noindex Page" at seam 4.
- [ ] 7.7 Drive "Canonical to a URL without a response" at seam 4.
- [ ] 7.8 Drive "Canonical to an indexable Page" and "Canonical to a non-HTML 200 response" at seam 4. This is a trivial pair: both targets count as indexable.
- [ ] 7.9 Drive "Canonical target never requested" at seam 4.
- [ ] 7.10 Drive "Noindex from X-Robots-Tag only" and "Noindex from both sources" at seam 4. This is a trivial pair: `detail.sources`. Register `noindex`.
- [ ] 7.11 Drive "Nofollow from meta robots" at seam 4, and register `nofollow`.
- [ ] 7.12 Drive "Meta refresh used" at seam 4, and register `meta-refresh`.
- [ ] 7.13 Docs: add the 5 canonical Rules and the 3 directive Rules to the catalogue in `docs/rules.md`.
- [ ] 7.14 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Content, URL and image Rules

- [ ] 8.1 Drive "Thin Page" and "Word count at the minimum" at seam 4. This is a trivial pair: one boundary.
- [ ] 8.2 Drive "Thin noindex Page is ignored" at seam 4.
- [ ] 8.3 Drive "Exact Duplicates" at seam 4, and register `exact-duplicate`.
- [ ] 8.4 Drive "Pages without a hash are not duplicates" at seam 4.
- [ ] 8.5 Drive "Uppercase letters in the path" and "Uppercase percent escapes are ignored" at seam 4. This is a trivial pair. Register `url-uppercase`.
- [ ] 8.6 Drive "Underscore in the path" and "Underscore only in the query" at seam 4. This is a trivial pair. Register `url-underscores`.
- [ ] 8.7 Drive "Parameters" at seam 4.
- [ ] 8.8 Drive "URL too long" and "URL at the limit" at seam 4. This is a trivial pair: one boundary. Register `url-too-long`.
- [ ] 8.9 Drive "Non-ASCII path" and "Non-ASCII host only" at seam 4. This is a trivial pair. Register `url-non-ascii`.
- [ ] 8.10 Drive "Images without alt text" at seam 4, and register `image-missing-alt-text`.
- [ ] 8.11 Drive "Srcset candidates are not counted twice" at seam 4.
- [ ] 8.12 Drive "All images described" at seam 4.
- [ ] 8.13 Drive "Image over the size limit" and "Image at the size limit" at seam 4. This is a trivial pair: one boundary. Register `image-too-large`.
- [ ] 8.14 Drive "Broken external image" at seam 4 by registering `image-broken`, the 42nd Rule. In the same red step, write "Catalogue size" and "Rule ids are unique kebab-case" at seam 1, which fail until this Rule exists.
- [ ] 8.15 Docs: add the 2 content Rules, 5 URL Rules and 3 image Rules to the catalogue in `docs/rules.md`, and check that the catalogue lists exactly the 42 ids that `spider rules list` returns.
- [ ] 8.16 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Health Score and per-Crawl configuration

- [ ] 9.1 Drive "Pages with Issue-type Issues lower the score" and "Score is rounded down" at seam 4, with the Health Score function. This is a trivial pair: one formula.
- [ ] 9.2 Drive "Warnings do not lower the score" at seam 4.
- [ ] 9.3 Drive "A Page with several Issues counts once" at seam 4.
- [ ] 9.4 Drive "Resource Issues do not change the score" at seam 4.
- [ ] 9.5 Drive "No Pages means no score" at seam 4.
- [ ] 9.6 Drive "Health Score of a Segment" at seam 4.
- [ ] 9.7 Drive "End-to-end score on the fixture site" at seam 3+6. Add the four `health_*` fields to the `crawl` row, written at the end of the post-crawl passes, with `health_calculated_at` from the injectable clock.
- [ ] 9.8 Drive "Score before the passes" at seam 3+6.
- [ ] 9.9 Drive "Later edits do not change a completed Crawl" at seam 2.
- [ ] 9.10 Drive "Resumed Crawl keeps the recorded configuration" at seam 3+6. Stop at `--max-urls`, then resume through the Crawl Service with a higher limit.
- [ ] 9.11 Docs: add the Health Score definition, the `health_*` fields, and how `050` and `070` call the function for Segments to `docs/rules.md`, with a link from `docs/architecture.md`.
- [ ] 9.12 Review: run the code-review skill on group 9's commits and then on the whole change, and refactor with the whole suite green.
