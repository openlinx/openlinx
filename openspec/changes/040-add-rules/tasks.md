> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task is one red → green slice and one commit (see docs/testing.md).
- **Red:** write the failing test for the named scenario at the named seam and watch it fail for the right reason.
- **Green:** write only the code that makes it pass, then run the whole suite.

Seams: 1 CLI, 2 services and store API, 4 pure-logic modules, 6 store contract. Every Rule is its reproducing query, so its slices run at seam 2, over a real crawl store (design D15). "Seam 3+6" means crawl the fixture site, then read the documented tables read-only.

- **Tables and columns.** There are no schema-first slices. A table or column is added in the slice whose scenario first needs it, with its `docs/schema.md` entry in the same commit, so `015-add-crawl-store`'s contract test is never red between commits.
- **Rules.** Each Rule is registered, with its final `description`, `why_it_matters` and `how_to_fix` texts, in the slice that first needs it.

**Releases:** v0.1 ships the 15 Rules of ROADMAP's "The v0.1 Rules" (the user's decision of 2026-10-05); the other 27 Rules of the catalogue are v0.2. Groups 1–4, 7 and 10 are v0.1 and group 9 is v0.2; in groups 5, 6 and 8 a task marked **(v0.2)** waits for v0.2, as the spec marks each requirement and scenario. A v0.1 scenario that names a v0.2 Rule is re-targeted to a v0.1 Rule, in the spec, before its task is driven; the tasks that still need it say so.

**The thin slice** (ROADMAP, Build order) is groups 1–4: the Rule model and `spider rules`, `[rules.<id>]` settings, the Rules as queries with stored and live Issues, and the slice's five Rules, `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing` and `h1-missing`, which `050`'s group 1 (`issues` and `issues <rule-id>`) reads. They need no redirects. Groups 5–10 widen.

**Order against `020` and `030`:** the slice starts once `020`'s first pull request (its groups 1–6: `urls` with `is_internal`, `in_scope`, `fetch_state`, `status_code`, `fetch_error`, `parsed` and `parse_error`) and `030`'s slice (its groups 1–3: `pages` with the title and heading columns) are on main. A Rule whose columns come later (`020`'s `blocked_by_robots_txt` in task 10.5; `022`-min's redirect and size columns; `030`'s Indexability, canonical, directive, link and content columns) is registered with a query that returns no rows until its own task, which names what it waits for where it is not obvious.

## 1. Rule model and the rules Command (slice)

- [x] 1.1 Drive "First Rule in the list" and "Every Rule has its guidance" at seam 1. This is a trivial pair: both fail until the registry and the Command exist. Add the Rule model, the registry, `internal-4xx` and `internal-5xx` with their guidance texts ("First Rule in the list" needs a second Rule for its `next_cursor`, and `internal-5xx` follows `internal-4xx` in the catalogue), and `spider rules list` on `010`'s output contract, with bare `spider rules` running `list`. `010`'s CLI has no Command groups yet, so this slice adds them in general (design D18): a group's Commands are registered under it, each with its own `@command_meta`, `spider commands` lists each by its full path (cli-contract: `rules list`), tested here, where `spider commands` first meets a group, and `--help` shows them. `060`'s `crawls list` reuses it.
- [x] 1.2 Drive "Show a Rule with thresholds" at seam 1. Register `title-too-long` with its thresholds and texts, and add `spider rules show <id>`.
- [x] 1.3 Drive "Rule without thresholds" at seam 1, and register `title-missing`.
- [x] 1.4 Drive "Unknown Rule id" at seam 1: `rule_not_found`, exit code 4, and a hint naming `spider rules list`.
- [x] 1.5 Drive "Windows console output" at seam 1, as a real subprocess on the Windows CI runner with code page 1251.
- [x] 1.6 Docs: create `docs/rules.md` covering the Rule model, what Issue Type and Priority mean, the Issue-type principle with `http-url` as Warning/High (design D3), category and id naming (D12) and how to read `spider rules` output.
- [x] 1.7 **Guard:** every code this change declares (design D17) is listed by `spider commands` with its level and exit code, at seam 1.
- [x] 1.8 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.
- [x] 1.9 Fixes from the approval of group 1, test-first: an option given before a grouped Command's name gets a hint that names that Command (the first argument that is one of the group's Commands, else the default), and a root option such as `--version` gets the root's hint; `spider --help` lists the group and `spider rules --help` exits 0; `build_app` refuses a top-level Command name with a space and a group name that a Command or another group already has (guard, red by mutation); the catalogue guard also checks that threshold defaults are at least 0 and that a Rule's threshold names are unique; two comments that restate the code go, and design Risks lists `test_rule_codes_are_self_described`.

## 2. Configuration in spider.toml (slice)

- [x] 2.1 Drive "Override shown by the rules Command" at seam 1, and add `[rules.<id>]` thresholds to `010`'s settings model. They fit neither of `010`'s table kinds (a flat model, or a keyed table with one entry model): each Rule has its own thresholds, and Rule ids hold `-`. So the `rules` table is a model built from the registry, with one field per Rule, aliased by its id, each an `extra="forbid"` model of `enabled` and its thresholds (integers, at least 0), registered in `build_app` beside `crawl` and `store`; `010`'s `check_table`, closest-key suggestion and `init` template learn it (the template gets one commented `[rules.<id>]` that points to `spider rules list`), and `crawl.config` dumps it by alias (design D9).
- [x] 2.2 Drive "Disabled Rule is listed" at seam 1 (`enabled = false`), and register `h1-missing`, whose query arrives with task 3.3, which gives a Rule registered before the slice of its condition a query that returns no rows until that slice (task 4.7 for `h1-missing`).
- [x] 2.3 Drive "Misspelt Rule id" at seam 1: `settings_invalid` with a dotted key and a closest-id hint, which names the Rule id (`title-too-long`), never its field name (`title_too_long`).
- [x] 2.4 Drive "Unknown key" at seam 1, on `h1-missing`. A test named after no scenario pins the suggestion inside a Rule table: `[rules.title-too-long]` `max_char = 70` gives the hint `rules.title-too-long.max_chars`, reached through the alias.
- [x] 2.5 Drive "Negative threshold" at seam 1. `spider crawl` exits 3, and the fixture site receives 0 requests, on `title-too-long`'s `max_chars`.
- [x] 2.6 Docs: add `[rules.<id>]` examples to `docs/rules.md`: raising a limit, disabling a Rule, and the error for a misspelt id; the `enabled` field joins the item fields it lists.
- [x] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.
- [x] 2.8 Close the approval of group 2: "Disabled Rule is listed" asserts that `h1-missing` is the only Rule that is off, so Rules being on by default is pinned (group 3's pass runs the Rules marked enabled); a Rule table named by the field name, `[rules.title_too_long]`, is `settings_invalid` with the hint `rules.title-too-long`, a guard against reading fields by name; the closest-key hint goes on to the next problem when one key cannot be followed, rather than giving no hint for the whole error; `docs/rules.md` says a threshold is at most 2^63-1, SQLite's largest INTEGER; "Template loads as defaults" runs over the tables of the tool and the fixture app, a table of named tables among them; the rules tests use `pytestmark` for their Workspace rather than an autouse fixture.
- [x] 2.9 A flat settings table refuses a setting whose type holds a table model anywhere, such as `list[Entry]`, `Entry | None` or `dict[str, Entry]`, since the template and the closest-key hint read flat tables only; a table of named tables, through its marker, stays the one table that holds tables (the rulings of 2026-10-14).

## 3. Rules as queries, stored Issues and live Issues (slice)

- [x] 3.1 Drive "Crawl records the thresholds it used" at seam 3+6. Create the `rules` table with every column of the spec but `reproduce_sql` (task 3.3), declared in `spider.store.schema` with the other public tables through `018`'s `public_table()`, which gains a `without_rowid` keyword here, its first user (`STRICT`, keyed by the Rule id, `WITHOUT ROWID` until task 3.18 left that to `affected_urls`; the contract test already compares `without_rowid`). Write the configuration snapshot in the transaction that creates the `crawl` row, through a new `rules` field on `015`'s `NewCrawl`, beside `section_crawl` (design D14).
- [x] 3.2 **Guard:** "Categories are an enumeration" at seam 6 (`values` on `rules.category`). Task 3.1 declares the values, which the column's CHECK needs, so it passes at once; red by mutation.
- [x] 3.3 Drive "The rules Command prints the reproducing query" at seam 1, with a Crawl started in the same Workspace. Add `reproduce_sql` to the Rule model, the `rules` table and the Command's items (design D15). A Rule registered before the slice of its condition carries a query that returns no rows until that slice.
- [x] 3.4 Drive "Missing title" at seam 2, through the evaluation entry point, which runs one Rule's query over a crawl file. The query reads `030`'s `title_count` and `title_1` from `pages` alone (design D2: the `urls.parsed` = 1 join waits for task 8.11). The test writes `urls` rows through `020`'s store units and `pages` rows through `030`'s `write_page` (`spider.store.pages`) with a `PageRow` (`spider.store.page_records`), only for a URL that is a Page by `030`'s predicate, as builders.
- [x] 3.5 Drive "Empty title counts as missing" at seam 2.
- [x] 3.6 Drive "Issues is a view" at seam 6. Create `affected_urls` and the `issues` view, declared in `spider.store.schema`. It is the schema's first view, so `018`'s declaration learns views: `spider schema` gives their `kind` `view`, the contract test compares the file's views, and `docs/schema.md` documents them (design D7).
- [x] 3.7 Drive "Issue row counts its Affected URLs" at seam 3+6. Add the post-crawl pass, in `spider.store.issues`, to `020`'s `default_hooks()` in `spider.services.hooks`: one unit per Rule that the Crawl's `rules` table marks enabled, which replaces its rows with `INSERT … SELECT` from the registry's query (design D5, D15). Check the units with `017`'s `replay_now(writer)`.
- [x] 3.8 Drive "A Rule's query returns its stored Affected URLs" at seam 3+6, over every enabled Rule. From here on it checks every Rule registered later.
- [x] 3.9 Drive "Keys of the Rule tables" at seam 6.
- [x] 3.10 Drive "Indexes of affected_urls" at seam 6.
- [x] 3.11 Drive "Issue Types are an enumeration" at seam 6 (`values` on `issues.issue_type`).
- [x] 3.12 Drive "Issue visible before the Crawl ends" at seam 3+6, with a fixture page that delays its response by 5 s: the Issues reader and its live path (design D16).
- [x] 3.13 Drive "A Crawl without a final pass is read live" at seam 2: the path chosen by the Crawl State. `resume` comes with `060`, so the test calls the pass, then writes `running` → `stopped` → `running` → `failed` with `020`'s `record_state`, which its transitions allow.
- [x] 3.14 Drive "Live and materialised Issues agree" at seam 3+6.
- [x] 3.15 Drive "Disabled Rule produces no Issue" at seam 3+6.
- [x] 3.16 **Guard:** "A failed extractor raises no Issue for its missing columns" at seam 2: the Page stays in `internal_pages`, and NULL columns fire nothing (design D2). It passes at once; red by mutation: the rejected `parse_error IS NULL` filter.
- [x] 3.17 Docs: add the `rules` and `affected_urls` tables and the `issues` view to `docs/rules.md`, with a sample query for each, how to run a Rule's `reproduce_sql` over a crawl file, and when Issues are live or materialised; the `reproduce_sql` field joins the item fields it lists.
- [x] 3.18 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.
- [x] 3.19 Drive the Issues of one URL at seam 2, a clause with no scenario of its own in "Issues of a Crawl without a final pass" (the reader returns "the Issues of one URL, in the shape of `affected_urls`"), which `050`'s `page <url>` calls: `read_url_issues`, with its path chosen by the Crawl State like the rest of the reader, one test per path, red first (the rulings of 2026-10-14).
- [x] 3.20 Close the approval of group 3: a read is one snapshot only in WAL mode, where snapshots are free, since in rollback-journal mode its SHARED lock would hold the writer's commit for the whole read; on the stored path, `read_affected_urls` knows a Rule by the file's own `rules` table, so every Rule that `read_issues` lists can be read; the live Issues of one URL leave out a disabled Rule (pinned); the test of "A Crawl without a final pass is read live" asserts that the first pass's rows remain; `docs/rules.md` runs a file's `reproduce_sql` only on the user's own file, and `docs/testing.md` lists `more_rules` and seam 2 for `tests/rules/`; design Risks says that rollback-mode reads are not one snapshot and that one failing Rule query fails a live read.
- [x] 3.21 Bound the writer's closing checkpoint: since task 3.18 a read holds one snapshot for its whole length, and `017`'s writer closes with a TRUNCATE checkpoint that waits for open reads up to the writer's 30 s busy limit, so a Crawl's end could stall while an agent reads its live Issues. The close checkpoints under a busy timeout of about 1 s, set for that statement alone, and accepts a busy result, which leaves the WAL to the last connection to close; red first at the store seam (the rulings of 2026-10-14). Undone by the review of group 4: a read-only connection never checkpoints, so the bound could leave a Crawl's last commits outside its file.

## 4. The slice's response code Rules and Missing H1 (slice)

- [x] 4.1 Drive "Client error" at seam 2, over `urls` rows: `020`'s `is_internal`, `fetch_state` and `status_code`. The `internal_urls` population reads `blocked_by_robots_txt` only from task 7.1, after `020` task 10.5 declares the column (design D2).
- [x] 4.2 Drive "External URLs are not Internal URLs" at seam 2.
- [x] 4.3 Drive "Client error recorded by a Crawl" at seam 3+6, with an Internal URL that is not a Page. `020`'s Crawl records it, Internal and not parsed, since group 6 of `020`.
- [x] 4.4 Drive "Server error" at seam 2, with `internal-5xx`'s query (registered in task 1.1).
- [x] 4.5 Drive "No response" at seam 2, over `020`'s `fetch_error`, and register `internal-no-response`.
- [x] 4.6 Drive "A URL that failed to be recorded is no Issue" at seam 2, with the reason in the query's SQL comment (design D15).
- [x] 4.7 Drive "Missing H1" at seam 2, over `030`'s `h1_count` and `h1_1`, replacing the query that returns no rows, which `h1-missing` carries from task 3.3 (registered in task 2.2).
- [x] 4.8 Docs: add the slice's five Rules (`internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing` and `h1-missing`) to the catalogue in `docs/rules.md`.
- [x] 4.9 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.
- [x] 4.10 Close the approval of group 4 (the rulings of 2026-10-14):
  - What the pass runs is exactly a Rule's `reproduce_sql`. The pass ends the wrapped text with a line break, so a trailing `--` comment no longer swallows the subquery's closing parenthesis.
  - A seam-4 catalogue guard checks that no Rule's query holds a `:name` that SQLAlchemy's `text()` would read as a bind parameter.
  - "A Rule's query returns its stored Affected URLs" covers all five slice Rules: `RULE_PAGES` gains a 503 and a reset connection.
  - `internal-no-response`'s description says "its site's robots.txt got no response".
  - The tests of tasks 3.8, 3.14, 4.3 and 3.21 state their premises: the comments name every page a Rule fires on, the Crawl is `completed`, and the reader's wait returned.
  - `crawl_with_url` takes `in_scope`, with a guard that an Internal URL outside the Scope is in `internal_urls`.
  - Design Risks says that a status outside every Rule's range raises no Issue.
- [x] 4.11 Read Issues at the connection level, so a Command reads them from one snapshot (the rulings of 2026-10-14, for `050`):
  - `spider.store.issues` gains `issues_in(connection, catalogue)` and `affected_urls_in(connection, rule_id, catalogue)`. They return Core selects in the shape of the `issues` view and of `affected_urls` for one Rule. The reader still alone chooses the stored or the live path, and `read_issues` and `read_affected_urls` become wrappers that run them in one `reading()`.
  - A test reads an Issue and its Affected URLs from one snapshot while the writer commits between them; red first.
  - `rule_not_found` gains `details.suggestions`: the closest ids of the Crawl's `rules` table on both paths, or of the catalogue for `spider rules show`; red first.
  - On the live path, a Rule that the file records but this tool's catalogue lacks is `rule_not_found`. Its message says that this tool cannot compute that Rule live, and its hint names `spider sql` with the Rule's `reproduce_sql`; red first.
  - D16 and design Risks follow.

## 5. Title Rules and the post-crawl pass (v0.1, except the tasks marked v0.2)

- [x] 5.0 Drive "A Page that was not parsed is not analysed" at seam 2 and "Populations are views" at seam 6 (design D19): every Rule's query selects from the view of its `population`, and one seam-2 test runs every Rule over a file with rows outside each population and checks that its Affected URLs are rows of its view.
- [x] 5.1 Drive "Title too long by characters" at seam 2.
- [x] 5.2 Drive "Title at the limit" at seam 2.
- [x] 5.3 Drive "Raised title limit" at seam 2: a Rule's query reads its thresholds from the Crawl's `rules` row (`json_extract`), so `reproduce_sql` runs on its own, with no threshold bound as a parameter (D15).
- [x] 5.4 Drive "Detail is stored as JSON" at seam 3+6, with the fixture page `/rules/long-title`.
- [ ] 5.5 **(v0.2)** Drive "Title too short" and "Title at the minimum" at seam 2. This is a trivial pair: one boundary. Register `title-too-short`.
- [ ] 5.6 **(v0.2)** Drive "Multiple titles" at seam 2, and register `title-multiple`.
- [x] 5.7 Drive "Rule that did not fire has no Issue" at seam 3+6.
- [ ] 5.8 **(v0.2)** Drive "Title equals H1" and "Comparison with H1 is case-sensitive" at seam 2. This is a trivial pair: the same comparison. Register `title-same-as-h1`.
- [x] 5.9 Drive "Duplicate titles among Indexable Pages" at seam 2, and register `title-duplicate`.
- [ ] 5.10 Drive "Non-indexable Pages are not compared" at seam 2. Its test is written in this group as a strict xfail that waits for `030`'s Indexability, which narrows `indexable_pages` (design D19); the task is done when the mark is gone, and v0.1 does not ship before.
- [x] 5.11 Drive "Duplicates found by the post-crawl passes" at seam 3+6, with the pass after `030`'s link counts.
- [x] 5.12 Drive "A running Crawl writes no Affected URL" at seam 3+6.
- [x] 5.13 Drive "A second pass does not duplicate rows" at seam 2. The pass replaces each Rule's rows in one unit per Rule.
- [x] 5.14 Merge `020` at the approved boundary of its group 9, which the rulings give and which includes its task 9.16, the post-crawl passes of a Crawl that `--max-urls` stops: until then such a Crawl ends `stopped` with no pass, and the reader would read its empty `affected_urls` as stored. Drive at seam 3 that a Crawl stopped by `--max-urls` lists its Issues as stored.
- [x] 5.15 Docs: add `title-too-long` and `title-duplicate` (id, type, priority, condition, detail, guidance) to the catalogue in `docs/rules.md`, with `title-too-long` checking characters only in v0.1. **(v0.2)** The other 3 title Rules.
- [x] 5.16 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green. Also, from the approval of task 4.11 (the rulings of 2026-10-14), `_found` escapes every `:` of a Rule's query as `\:` for SQLAlchemy's `text()`, so the text that runs equals `reproduce_sql` whatever it holds; this closes the class that the bind-parameter guard of task 4.10 only enumerates, and the guard goes with it (red first: a Rule whose comment holds ` :later` runs as written).
- [ ] 5.17 Close the approval of group 5: the population test covers title-duplicate's join, a seam-1 test pins every Rule's `applies_to`, the xfail of "Non-indexable Pages are not compared" is conditioned on PageRow's fields, and design and docs describe what is built.

## 6. Meta description and heading Rules (v0.1, except the tasks marked v0.2)

- [ ] 6.1 Drive "Missing meta description" at seam 2, and register `meta-description-missing`.
- [ ] 6.2 **(v0.2)** Drive "Meta description too long" and "Meta description at both limits" at seam 2. This is a trivial pair: one boundary. Register `meta-description-too-long`.
- [ ] 6.3 **(v0.2)** Drive "Meta description too short" at seam 2, and register `meta-description-too-short`.
- [ ] 6.4 **(v0.2)** Drive "Multiple meta descriptions" at seam 2, and register `meta-description-multiple`.
- [ ] 6.5 **(v0.2)** Drive "Duplicate meta descriptions" at seam 2, and register `meta-description-duplicate`.
- [ ] 6.6 **(v0.2)** Drive "Multiple H1" at seam 2, and register `h1-multiple`.
- [ ] 6.7 **(v0.2)** Drive "H1 too long" and "H1 at the limit" at seam 2. This is a trivial pair: one boundary. Register `h1-too-long`.
- [ ] 6.8 **(v0.2)** Drive "Duplicate H1" at seam 2, and register `h1-duplicate`.
- [ ] 6.9 **(v0.2)** Drive "Missing H2" at seam 2, over `030`'s `h2_count` and `h2_1`, and register `h2-missing` (moved from group 3).
- [ ] 6.10 Docs: add `meta-description-missing` to the catalogue in `docs/rules.md`. **(v0.2)** The other 4 meta description Rules and the other 4 heading Rules.
- [ ] 6.11 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Response code and security Rules (v0.1)

- [ ] 7.1 Drive "Blocked even when crawled anyway" at seam 2, after `020` task 10.5, and register `internal-blocked-by-robots-txt`; the `internal_urls` population gains `blocked_by_robots_txt` = 1 here (design D2).
- [ ] 7.2 Drive "Internal redirect" at seam 2, and register `internal-3xx`.
- [ ] 7.3 Drive "Two-hop chain" and "One hop is not a chain" at seam 2. This is a trivial pair: the walk along `redirect_url_id` and its boundary. Register `redirect-chain`.
- [ ] 7.4 Drive "Loop" at seam 2, using `in_redirect_loop`. Register `redirect-loop`.
- [ ] 7.5 Drive "Content served over HTTP" and "HTTP URL that redirects to HTTPS" at seam 2. This is a trivial pair. Register `http-url` as Warning/High.
- [ ] 7.6 Docs: add the other 4 response code Rules and `http-url` to the catalogue in `docs/rules.md`.
- [ ] 7.7 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Canonical and directive Rules (v0.1, except the tasks marked v0.2)

- [ ] 8.1 **(v0.2)** Drive "Missing canonical" and "Noindex Page needs no canonical" at seam 2. This is a trivial pair. Register `canonical-missing`.
- [ ] 8.2 **(v0.2)** Drive "Canonicalised Page" at seam 2, and register `canonicalised`.
- [ ] 8.3 **(v0.2)** Drive "Relative canonical" at seam 2, and register `canonical-relative`.
- [ ] 8.4 **(v0.2)** Drive "Conflicting canonicals" and "Agreeing canonicals" at seam 2. This is a trivial pair. Register `canonical-conflicting`.
- [ ] 8.5 Drive "Canonical to a redirect" at seam 2, with the target's Indexability in the Rule's reproducing query (design D13). Register `canonical-to-non-indexable`.
- [ ] 8.6 Drive "Canonical to a noindex Page" at seam 2.
- [ ] 8.7 Drive "Canonical to a URL without a response" at seam 2.
- [ ] 8.8 Drive "Canonical to an indexable Page" and "Canonical to a non-HTML 200 response" at seam 2. This is a trivial pair: both targets count as indexable.
- [ ] 8.9 Drive "Canonical target never requested" at seam 2.
- [ ] 8.10 Drive "Noindex from X-Robots-Tag only" and "Noindex from both sources" at seam 2. This is a trivial pair: `detail.sources`. Register `noindex`.
- [ ] 8.11 Drive "Non-analysed Pages are skipped by Page Rules" at seam 2, with a Page that responded 404 with an HTML body and `X-Robots-Tag: noindex`, whose `x_robots_tag_noindex` `030` reads from the headers of any Page (its task 6.2). `analysed_pages` holds the `urls.parsed` = 1 join since task 5.0, so the test is red by mutation of the view.
- [ ] 8.12 **(v0.2)** Drive "Nofollow from meta robots" at seam 2, and register `nofollow`.
- [ ] 8.13 **(v0.2)** Drive "Meta refresh used" at seam 2, and register `meta-refresh`.
- [ ] 8.14 Drive "Catalogue size" (15), and add "Rule ids are unique kebab-case" as a guard (the catalogue guard of task 1.8 already holds unique ids), at seam 1, once `noindex`, the last of the 15 v0.1 Rules, is registered; group 9 raises the size to 42 in v0.2.
- [ ] 8.15 Docs: add `canonical-to-non-indexable` and `noindex` to the catalogue in `docs/rules.md`, and check that it lists exactly the 15 ids that `spider rules list` returns. **(v0.2)** The other 4 canonical Rules and the other 2 directive Rules.
- [ ] 8.16 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. (v0.2) Content, URL and image Rules

- [ ] 9.1 Drive "Thin Page" and "Word count at the minimum" at seam 2. This is a trivial pair: one boundary.
- [ ] 9.2 Drive "Thin noindex Page is ignored" at seam 2.
- [ ] 9.3 Drive "Exact Duplicates" at seam 2, and register `exact-duplicate`.
- [ ] 9.4 Drive "Pages without a hash are not duplicates" at seam 2.
- [ ] 9.5 Drive "Uppercase letters in the path" and "Uppercase percent escapes are ignored" at seam 2. This is a trivial pair. Register `url-uppercase`.
- [ ] 9.6 Drive "Underscore in the path" and "Underscore only in the query" at seam 2. This is a trivial pair. Register `url-underscores`.
- [ ] 9.7 Drive "Parameters" at seam 2.
- [ ] 9.8 Drive "URL too long" and "URL at the limit" at seam 2. This is a trivial pair: one boundary. Register `url-too-long`.
- [ ] 9.9 Drive "Non-ASCII path" and "Non-ASCII host only" at seam 2. This is a trivial pair. Register `url-non-ascii`.
- [ ] 9.10 Drive "Images without alt text" at seam 2, and register `image-missing-alt-text`.
- [ ] 9.11 Drive "Srcset candidates are not counted twice" at seam 2.
- [ ] 9.12 Drive "All images described" at seam 2.
- [ ] 9.13 Drive "Image over the size limit" and "Image at the size limit" at seam 2. This is a trivial pair: one boundary. Register `image-too-large`.
- [ ] 9.14 Drive "Broken external image" at seam 2 by registering `image-broken`, the 42nd Rule. In the same red step, "Catalogue size" moves to 42 (v0.2) and "Rule ids are unique kebab-case" checks every id, both of task 8.14.
- [ ] 9.15 Drive "An image that failed to be recorded is not broken" at seam 2, with the reason in the query's SQL comment.
- [ ] 9.16 Docs: add the 2 content Rules, 5 URL Rules and 3 image Rules to the catalogue in `docs/rules.md`, and check that the catalogue lists exactly the 42 ids that `spider rules list` returns.
- [ ] 9.17 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Health Score and per-Crawl configuration (v0.1, except the task marked v0.2)

- [ ] 10.1 Drive "Pages with Issue-type Issues lower the score" and "Score is rounded down" at seam 4, with the Health Score function. This is a trivial pair: one formula.
- [ ] 10.2 Drive "Warnings do not lower the score" at seam 4.
- [ ] 10.3 Drive "A Page with several Issues counts once" at seam 4. Its `exact-duplicate` is v0.2: re-target the scenario to a v0.1 Issue-type Rule first.
- [ ] 10.4 **(v0.2)** Drive "Resource Issues do not change the score" at seam 4.
- [ ] 10.5 Drive "No Pages means no score" at seam 4.
- [ ] 10.6 Drive "Health Score of a Segment" at seam 4.
- [ ] 10.7 Drive "End-to-end score on the fixture site" at seam 3+6. Add the four derived `health_*` fields to the `crawl` row, with `Derived: ` descriptions, written only by the pass's last unit, with `health_calculated_at` from the injectable clock.
- [ ] 10.8 Drive "Health fields are derived" at seam 6.
- [ ] 10.9 Drive "Score before the passes" at seam 3+6.
- [ ] 10.10 Drive "Later edits do not change a completed Crawl" at seam 2. Its `low-word-count` is v0.2: re-target the scenario to a v0.1 Rule with a threshold (`title-too-long`'s `max_chars`) first.
- [ ] 10.11 Drive "Resumed Crawl keeps the recorded configuration" at seam 3+6. Stop at `--max-urls`, then resume through the Crawl Service with a higher limit. Its `low-word-count` and `word_count` are v0.2: re-target the scenario to `title-too-long`'s `max_chars` and `title_1_length` first.
- [ ] 10.12 Docs: add the Health Score definition, the `health_*` fields, and how `050` and `070` call the function for Segments to `docs/rules.md`, with a link from `docs/architecture.md`.
- [ ] 10.13 Review: run the code-review skill on group 10's commits and then on the whole change, and refactor with the whole suite green.
