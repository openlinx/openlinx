> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

The motivation is in proposal.md, and the catalogue and behaviour are in `specs/rules/spec.md`. Ownership follows [ROADMAP.md](../../../ROADMAP.md) ("What each change owns"). Rules read three sources:

- the `urls` table of `020-add-crawl-core`, with the fetch columns of `022-add-fetch-policy`:
  - Internal/External, `status_code`, `fetch_state` and `fetch_error`
  - `blocked_by_robots_txt`, `redirect_url_id` and `in_redirect_loop`
  - `size_bytes` and `parsed`
- the `pages` and `links` tables, the stored Indexability and the link counts of `030-add-page-data`
- the Workspace settings loaded and validated by `010-add-workspace-and-cli-contract`

`020-add-crawl-core` provides (its D9 and D14):

- a **per-response hook** of pure handlers, which runs for every recorded URL. A handler returns rows, and the crawl store writes them in the writer unit that records the URL.
- a **post-crawl passes** hook of store functions, which runs when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written, and again after every continued run, so a pass must be safe to re-run

`015-add-crawl-store` provides the `crawl` row and the writer. `017-speed-up-crawl-writer` sets the contract of a unit (its D7): a unit may run again before its commit, so it is deterministic, has no effect outside its connection and returns values only. `018-add-schema-conventions` sets the schema conventions of [ADR-0005](../../../docs/adr/0005-crawl-file-schema-conventions.md) and the declaration helper every table goes through. Issues must be queryable while a Crawl runs. Crawls can reach about 500k URLs.

## Goals / Non-Goals

**Goals:**
- Deterministic Issues with fixed guidance that an agent can explain without judgement calls ([ADR-0004](../../../docs/adr/0004-tool-never-calls-an-llm.md)).
- A Health Score that means the same in every Crawl and for every Segment.
- Crawl files that explain their own Issues, even when they are opened by another tool version.
- Every Rule condition computable from stored data alone, so v0.2's `rules apply` can recompute Issues without re-crawling.

**Non-Goals:**
- Site-wide link-graph Rules and `rules apply` (v0.2), structured-data validation (v0.3) and Rule plugins (backlog).
- Per-Segment Issue lists and Health Scores at query time; these belong to `050`, which calls this change's function.
- A declarative rule language.

## Decisions

### D1. Rules are a code registry
Each Rule is a registered object with its metadata (the spec's Rule model) and one condition.
- **`during_crawl` Rules** are pure functions. They take one Page record with its Links, or one `urls` row, plus the effective thresholds, and return zero or one Affected URL with its `detail`.
- **`post_crawl` Rules** are evaluated by their reproducing queries (D15), in SQL over the store:
  - `GROUP BY` for duplicates
  - joins against `urls` and `pages` for canonical targets and image Resources
  - a recursive walk along `redirect_url_id` for Redirect Chains
  - `022`'s `in_redirect_loop` flag for loops
- *Alternative: declarative YAML/JSON conditions.* Rejected. Conditions combine several columns, other URLs' outcomes and, for duplicates, grouping. A condition language would duplicate the `--where` language of `050`, and would still need code for Redirect Chains. The YAML approach stays for v0.3's structured-data validators, where the data is naturally declarative.

### D2. Populations and whose URL is affected
- **Page Rules** see only analysed Pages (`urls.parsed` = 1).
- **Comparison Rules and thin content** (duplicates, `exact-duplicate`, `low-word-count`) see only Indexable Pages. Pages that are canonicalised or noindexed by intent are then not reported as duplicates of the Pages they point to. Screaming Frog behaves the same way.
- **`image-too-large` and `image-broken`** affect the image URL, because one fix to one file clears every Page that uses it.
- **`image-missing-alt-text`** affects the Page, because the `alt` attribute is part of the Page's HTML. It counts only `<img src>` Links, so the `srcset` candidates that `020` also discovers are not counted twice.
- *Consequence:* Resource Issues never change the Health Score, which is defined over Internal Pages (see Open Questions).

### D3. What makes a Rule Issue-type
`issue` is reserved for definite defects, because Issue-type Issues alone drive the Health Score. There are 10 of them:

- `internal-4xx`, `internal-5xx`, `internal-no-response` and `redirect-loop`
- `title-missing` and `title-multiple`
- `canonical-to-non-indexable` and `canonical-conflicting`
- `exact-duplicate`
- `image-broken`

Anything that can be intentional, or that the maintainer does not want to lower the score, is a `warning`: noindex, canonicalised, blocked by robots.txt, redirects, missing canonical or H1, and `http-url`. Improvements are `opportunity`. Priorities follow Screaming Frog's where they are known.
- **`http-url`** is a Warning with High Priority, a decision the maintainer made on 2026-09-27. A site served over plain HTTP is flagged prominently, but its Health Score still reflects its other defects.
- *Alternative: copy Screaming Frog's Issue Types everywhere.* Rejected. They are not fully documented, and several are Opportunities that would hide definite defects from the Health Score.
- *Consequence:* changing a Rule's Issue Type later changes Health Scores. It is treated as a contract change and noted in the changelog.

### D4. 42 Rules
The maintainer approved keeping all 42 Rules on 2026-09-27. Noindex and nofollow each combine meta robots and X-Robots-Tag: the problem is the same, and `detail.sources` tells the agent where to fix it. Every Rule has a distinct fix. The low-value Rules (`title-same-as-h1`, `h1-too-long`, `url-underscores`, `url-parameters`, `meta-description-too-short`) are `opportunity`/`low`, so they do not touch the Health Score and sort last in Reports. Each one can be disabled with `enabled = false`.

### D5. When Rules run
- **During the Crawl.** This change's per-response handler evaluates the URL Rules for every recorded URL, and the Page Rules with the Page's data from `030` for analysed Pages. It is pure: it returns the URL's Affected URLs as frozen rows declared in `spider.store`, and the URL's writer unit writes them through `spider.store.issues` (`020` D9, D14). The `issues` view counts them as they commit (D7), so partial Crawls show consistent Issues.
- **In the post-crawl passes.** Rules that need other records wait for the passes:
  - duplicates
  - canonical targets, which may be fetched later
  - Redirect Chains and loops, which are complete only when every hop has been fetched
  - image Resources, whose checks may finish after the Page
- **Order.** Through `020`'s hook, the passes run in this order:
  1. `030` link counts
  2. `040` `post_crawl` Rules
  3. the Health Score
- **When they run.** They run for Crawls that end as `completed` or `stopped`, and again when a resumed Crawl ends. The pass is a store function in `spider.store.issues`. It submits one writer unit per `post_crawl` Rule, which deletes the Rule's rows and inserts what its reproducing query returns, so a second run replaces the first. Nothing is recounted, because `issues` is a view. `failed` and `interrupted` Crawls get the passes only once they are resumed and end.

### D6. Each Crawl records its Rule configuration
When the Crawl starts, the `rules` table records every Rule's type, priority, enabled state, effective thresholds, guidance texts and reproducing query.
- *Why:* crawl files stay self-contained ([ADR-0002](../../../docs/adr/0002-sqlite-crawl-store-public-schema.md)). A resumed Crawl keeps the configuration it started with. A Report built later shows the thresholds that produced its Issues, and the guidance texts are available even to a reader without the same tool version.
- *Alternative: store only the Rule ids and read metadata from the installed tool.* Rejected. The thresholds used would be lost, and texts could silently change.

### D7. `issues` is a view over `affected_urls`
No count of Affected URLs is stored: a count that only repeats the rows of another table is not stored (ADR-0005), so `issues.affected_count` was dropped. `issues` is a view that joins `rules` with the count of each Rule's rows in `affected_urls`, read over the primary key's `rule_id` prefix (ruling Q12).
- It cannot disagree with `affected_urls`, it is right while the Crawl runs, and the post-crawl pass has nothing to recount.
- It keeps the name and columns that `050`'s `issues` Command and export and `070`'s Report read, `affected_count` included.
- *Cost:* each read of `issues` counts the rows of `affected_urls`, a scan of its primary key.
- **The first view of the schema.** `018`'s `spider schema` already lists a `kind` of `table` or `view`. This change declares the view in `spider.store.issues`, next to its description, column descriptions and `values`, and extends `018`'s contract test to views: the file must have the view, with its column names in order. SQLite reports no `NOT NULL` and its own type names for a view's computed columns (`INT` for a `CAST(… AS INTEGER)`), so a view's types and nullability come from the declaration only, and `STRICT` is checked for tables only.
- *Alternative: a real table, updated with `affected_urls`,* as the draft had. It stores a count of other rows, and every write and every pass must keep it right. Rejected by ADR-0005.
- *Alternative: no `issues` object in the file,* only `050`'s query. Agents writing SQL would have to know the join. Rejected.
- *Alternative: build `issues` only at the end.* Rejected, because partial Crawls would show Affected URLs without Issues.

### D8. The Health Score
- **Formula.** `floor(100 × (N − A) ÷ N)`. Rounding down means 100 is shown only when no Page has an Issue-type Issue.
- **Storage.** The score is stored as four crawl metadata fields on the one-row `crawl` table (`health_score`, `health_internal_pages`, `health_affected_pages`, `health_calculated_at`).
  - *Alternative: a one-row `health_score` table.* Rejected. ADR-0005 requires table names to be plural nouns, with `crawl` as the only one-row exception.
  - They are derived (ADR-0005): only the post-crawl pass writes them, after the `post_crawl` Rules, and each description starts with `Derived: `. They stay NULL until the pass runs.
  - `health_score` has no unit suffix, because a score is not a share (ADR-0005 rule 5; it was `health_score_pct` until ruling Q9). The other names follow `050`'s summary shape `{score, internal_pages, affected_pages}`.
  - `health_calculated_at` comes from the injectable clock.
- **Subsets.** The formula is exposed as one pure function taking the set of Internal Pages and the set of URLs affected by Issue-type Rules. `050` (Segments) and `070` (health per Segment) call it, rather than re-implementing it.
- **Which Issue Types count.** They are read from the Crawl's `rules` table, never from the installed tool.

### D9. Strict configuration through `010`'s settings validation
`[rules.<id>]` tables are part of the settings model, which `010` validates eagerly whenever settings load. Unknown ids, unknown keys and bad values become `settings_invalid` problems with dotted keys, such as `rules.title-to-long`, and a hint naming the closest known id or key. A silent typo would quietly change audit results. The cost is that a `spider.toml` written for a newer version, with new Rule ids, fails on an older tool; the message names the unknown id, so the fix is obvious.

The table names are Rule ids. They mirror no flag, so `010`'s flag-mirroring key rule does not apply to them.

### D10. Changing thresholds after a Crawl
v0.1 does not recompute stored Issues. A Crawl is judged by the configuration it recorded. `rules apply` (v0.2, in ROADMAP.md) will recompute Issues from stored data. That works because every condition reads only stored data (D1).

### D11. `spider rules` describes the Workspace, not a Crawl
`spider rules` shows what the next Crawl will use. What an earlier Crawl used is in that Crawl's `rules` table, which `050`'s `issues` output and `spider sql` can show.
- *Alternative: accept `--crawl` and show the recorded snapshot.* Deferred to avoid a second meaning for the same Command.

### D12. Category values are snake_case, Rule ids are kebab-case
Categories are stored enumeration values, and `015` requires enumeration values to match `^[a-z][a-z0-9_]*$`. So they are `response_codes`, `meta_descriptions` and so on. `070` maps them to its kebab-case Report Section ids. Rule ids are free text that people type as command arguments and as `spider.toml` table names, where TOML bare keys allow `-`. They keep the kebab-case form of the approved design.

### D13. Canonical targets use 030's Indexability
`canonical-to-non-indexable` fires when the target's Indexability is non-indexable, not on "any non-200":
- **When the target is a Page,** that is the stored `indexability` of `030`.
- **When the target is not a Page,** `030` stores no Indexability, so the Rule applies steps 1–4 of `030`'s order (robots.txt, 3xx, 4xx, 5xx) to its `urls` row, plus `no_response` for a request that got no response.

A 2xx non-HTML target, such as a PDF, therefore counts as indexable, as it would for `030`. A target that was never requested is not judged.
- *Alternative: store Indexability for every Internal URL.* It would add Indexability columns to `020`'s `urls` table, which the v0.1 schema blueprint does not have. It is left to `030`'s Open Questions.

### D14. The tables under ADR-0005
The schema blueprint of 2026-10-11 and its rulings decide these tables before they are built. Each goes through `018`'s declaration helper, so it is `STRICT`, and its enumerations and flags get CHECKs from the declared values.
- **`rules`:** keyed by `id`, the Rule id, as TEXT: a public identifier that a user types (ADR-0005 rule 2). It is `WITHOUT ROWID`, because the Rule id is its natural key and it holds about 42 rows.
  - `category`, `issue_type`, `priority`, `applies_to` and `evaluation` are enumerations whose values are `Literal`s in `spider.store.records`, as `020`'s are, so the code, the CHECK and `values` cannot disagree.
  - `reproduce_sql` holds the Rule's query (ruling Q11, D15).
  - **When it is written:** in the transaction that creates the `crawl` row. This change adds a `rules` field to `015`'s `NewCrawl`, as `020` added `scope`, and `create_crawl` writes its rows. Every `affected_urls` row can then reference a `rules` row from the first unit on, and a Crawl that dies before its first unit still records its configuration.
- **`affected_urls`:** keyed by `(rule_id, url_id)`, `WITHOUT ROWID`, as a table of pairs with narrow rows (rule 15). Both columns are declared references.
  - `affected_urls_url_id` on `url_id`: it serves the Issues of one URL (`050`'s `page <url>`) and the Health Score's count of affected Pages. A query by Rule uses the primary key's prefix and needs no index.
  - `detail` is JSON, nullable: nothing filters on it in v0.1 (rule 11).
- **`issues`:** a view (D7).
- **The `crawl` fields:** D8.

### D15. Reproducing queries
Every Rule ships one SQL query over the public schema that reproduces its Affected URLs (ROADMAP, 2026-10-05). It is what lets an agent that reads only the crawl file check an Issue, and it is the base of v0.3's User SQL Rules.
- **Shape:** a read-only `SELECT` that returns `url_id` and `detail`. It reads the effective thresholds from the Crawl's `rules` row, for example `json_extract((SELECT thresholds FROM rules WHERE id = 'low-word-count'), '$.min_words')`. Its text is then a constant of the Rule: the same in every Workspace and Crawl, and still right under overrides.
- **`post_crawl` Rules are evaluated by it:** the pass's unit runs `INSERT INTO affected_urls (rule_id, url_id, detail) SELECT :rule_id, url_id, detail FROM (<query>)`. Each statement is built once, at import (`017` D9). The unit reads only the file, so it is deterministic when it runs again (`017` D7).
- **`during_crawl` Rules stay in Python,** in the per-response handler, so their Issues appear while the Crawl runs. One test at seam 3+6 runs every enabled Rule's query over a fixture Crawl and compares the rows with the stored ones, so the two forms of a Rule cannot drift apart unnoticed.
- **Where it is read:** `rules.reproduce_sql` in the file, and `spider rules list` and `show`.
- *Alternative: per-Rule Python for `post_crawl` Rules too,* as the draft had (grouping, the chain walk and target Indexability as pure functions). Each Rule would then exist twice. Rejected: `020` D9 already runs these Rules by their queries.

## Test seams

The seams come from [docs/testing.md](../../../docs/testing.md). No new seam is introduced:

- **Seam 4, pure-logic modules.**
  - Every catalogue scenario is tested here as a table-driven case: a Page record with its Links, or a `urls` row, in; fires or not, with the literal `detail`, out.
  - The Health Score function is tested here as well.
  - Test-data builders for Page records and `urls` rows are builders, not test doubles.
- **Seam 2, services and store API.**
  - `post_crawl` Rules are tested by calling the post-crawl pass of `spider.store.issues` on a real crawl store in a temporary Workspace, whose rows are written through the store's writers: duplicate grouping, canonical target Indexability, the Redirect Chain walk and the image Resource checks.
  - A direct call runs the pass twice, to test idempotency. "Later edits do not change a completed Crawl" is tested the same way.
  - The store units are checked with `017`'s `replay_now(writer)`, which makes the writer run them again.
- **Seam 3+6, fixture site plus store contract.** End-to-end slices crawl fixture pages under `/rules/` and read `rules`, `issues`, `affected_urls` and the `crawl` row through the documented tables, read-only. One of them runs every Rule's reproducing query against the stored rows (D15). `http-url` is a Warning, so the plain-HTTP fixture site does not lower the Health Score in these slices.
- **Seam 6, store contract.** `spider schema` is compared with hand-written `values` lists, keys and indexes, and `018`'s contract test covers the new tables and the view.
- **Seam 1, CLI.** This covers `spider rules list` and `show`, the `settings_invalid` and `rule_not_found` errors and their exit codes, and one real subprocess run on Windows with console code page 1251.
- **Boundary doubles.** Only the injectable clock, for `health_calculated_at`. Our own modules are never mocked.

## Risks / Trade-offs

- [An `http`-only site gets `http-url` on every Page] → It is a Warning/High, so it tops the Warnings in Reports without lowering the Health Score, as the maintainer decided. The guidance explains the fix.
- [Broken internal images are reported by both `internal-4xx` and `image-broken`] → Accepted, as in Screaming Frog. One is about the URL and one about its use as an image. The fixes point to the same file.
- [Resource and non-Page URL Issues, such as no response or blocked, do not lower the Health Score] → This follows the glossary definition, which is Page-centric. It is documented, and listed under Open Questions.
- [Duplicate grouping on about 500k Pages] → Plain `GROUP BY` over non-NULL values, which is O(n log n) in SQLite with no extra index. The passes run once per Crawl end.
- [Each read of `issues` counts `affected_urls`] → A scan of its primary key, which a Crawl of about 500k URLs keeps to a few million narrow rows. `050` reads it once per Command.
- [A Rule's Python condition and its query could disagree] → One end-to-end test compares them for every enabled Rule (D15).
- [Some Priorities differ from Screaming Frog's] → The documented principle (D3) applies, and `docs/rules.md` lists every Rule's type and priority.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds `rules`, `affected_urls`, the `issues` view and the four `health_*` fields of `crawl` to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5).

## Open Questions

These can be answered later without changing this change's specs or tasks:

1. **Resource Issues and the Health Score.** Should Resource Issues count against the Health Score, by attributing each one to the Pages that reference the Resource?
2. **Overriding Issue Type and Priority.** Should `spider.toml` be able to change a Rule's Issue Type or Priority, and if so, how do Health Scores stay comparable?
3. **Which redirects `internal-3xx` reports.** Should it report only redirecting URLs that are linked from Pages, or also intermediate hops reached only through other redirects?
4. **Case-insensitive duplicates.** Should duplicate comparisons (titles, meta descriptions, H1) ignore case?
