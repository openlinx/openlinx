## Context

The motivation is in proposal.md, and the catalogue and behaviour are in `specs/rules/spec.md`. Ownership follows [ROADMAP.md](../../../ROADMAP.md) ("What each change owns"). Rules read three sources:

- the `urls` table of `020-add-crawl-core`, with the fetch columns of `022-add-fetch-policy`:
  - Internal/External, `status_code`, `fetch_state` and `fetch_error`
  - `blocked_by_robots_txt`, `redirect_url_id` and `in_redirect_loop`
  - `size_bytes` and `parsed`
- the `pages` and `links` tables, the stored Indexability and the link counts of `030-add-page-data`
- the Workspace settings loaded and validated by `010-add-workspace-and-cli-contract`

**What the slice (tasks.md) reads:**
- **`020`'s `urls`, through its first pull request:** `is_internal` and `in_scope` (NOT NULL flags), `fetch_state`, `skip_reason`, `status_code`, `fetch_error` with `fetch_error_message`, `content_type`, `parsed`, and `parse_error` with `parse_error_message`, declared in `spider.store.schema` with their value lists as `Literal`s in `spider.store.records`. `blocked_by_robots_txt` comes with `020`'s robots.txt handling, and `022`-min adds `redirect_url_id`, `in_redirect_loop` and `size_bytes`.
- **`030`'s `pages`:** `pages` is declared in `spider.store.schema` with the other public tables, its row is the frozen `PageRow` in `spider.store.page_records`, which `write_pages` in `spider.store.pages` writes, and its per-response handler is `page_rows` in `spider.extract.page_handler`, listed in `default_hooks()`, which gives a row only to a Page: an Internal URL in the Scope (`is_internal` = 1, `in_scope` = 1), `fetched`, with an HTML media type by `020`'s `is_html_type`, whatever its status. `030`'s slice adds `title_count`, `title_1`, `title_1_length`, `title_2`, the meta description columns and the `h1_*` and `h2_*` columns; Indexability and the link counts arrive later in `030`.
- **Seam-2 test data** is written through those modules' own row writers, as builders: `020`'s units in `spider.store.urls`, and `030`'s `write_pages` with a `PageRow` only for a URL that is a Page by that predicate, so the data is what a real Crawl could leave.

`020-add-crawl-core` provides (its D9 and D14), through `Hooks` in `spider.crawl.hooks`, whose built-in entries `default_hooks()` lists in `spider.services.hooks`, the composition root, so the crawl core never imports its plugins:

- a **per-response hook** of pure handlers, which this change does not use (D1)
- a **post-crawl passes** hook of store functions (`Pass`: a name and a function of the `CrawlWriter`), which runs when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written, and again after every continued run, so a pass must be safe to re-run

`015-add-crawl-store` provides the `crawl` row and the writer. `017-speed-up-crawl-writer` sets the contract of a unit (its D7): a unit may run again before its commit, so it is deterministic, has no effect outside its connection and returns values only. `018-add-schema-conventions` sets the schema conventions of [ADR-0005](../../../docs/adr/0005-crawl-file-schema-conventions.md) and `public_table()`, which every public table goes through. Issues must be queryable while a Crawl runs. Crawls can reach about 500k URLs.

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

### D1. Rules are a code registry of SQL queries
**In short:** each Rule is a registered object whose reproducing query is the only form of its condition, and no Rule runs while a URL is recorded.

Its metadata is the spec's Rule model. The queries cover every kind of condition:
- column conditions on one `urls` or `pages` row
- `GROUP BY` for duplicates
- joins against `urls` and `pages` for canonical targets and image Resources
- a recursive walk along `redirect_url_id` for Redirect Chains
- `022`'s `in_redirect_loop` flag for loops

So the Crawl's writer, the bottleneck of a Crawl, writes no Affected URL, and each Rule exists once.
- *Alternative: Python conditions in a per-response handler, with the query checked against them.* Each Rule would exist twice, kept together by an equality test, and every Issue would add rows and index entries to the writer's units. Rejected.
- *Alternative: declarative YAML/JSON conditions.* Rejected. Conditions combine several columns, other URLs' outcomes and, for duplicates, grouping. A condition language would duplicate the `--where` language of `050`, and would still need code for Redirect Chains. The YAML approach stays for v0.3's structured-data validators, where the data is naturally declarative.

### D2. Populations and whose URL is affected
**In short:** URL Rules read the requested or robots-blocked Internal URLs, Page Rules the analysed Pages, and comparison Rules only the Indexable ones. An image Issue affects the image URL, except missing alt text, which affects the Page.
- **`internal_urls`** is `is_internal` = 1 with `fetch_state` `fetched` or `error`, or with `blocked_by_robots_txt` = 1, which holds whether or not the URL was fetched under `--ignore-robots`. The response code Rules keep their own `fetch_state` and status or `fetch_error` conditions, so a blocked URL that was not fetched raises none of them.
- **Page Rules** see only analysed Pages (`urls.parsed` = 1), through `analysed_pages` (D19).
- **A Page whose extractor failed** (`parse_error` = `extractor_error`) stays among them. The columns its failed extractor fills are NULL, and a Rule never fires on a NULL value, so it raises no false Issue, while the columns of the extractors that succeeded are still checked. *Alternative:* `parse_error IS NULL` in `internal_pages`. It would hide every Issue of a Page whose unrelated extractor failed. Rejected.
- **Comparison Rules and thin content** (duplicates, `exact-duplicate`, `low-word-count`) see only Indexable Pages. Pages that are canonicalised or noindexed by intent are then not reported as duplicates of the Pages they point to. Screaming Frog behaves the same way.
- **`image-too-large` and `image-broken`** affect the image URL, because one fix to one file clears every Page that uses it.
- **`image-missing-alt-text`** affects the Page, because the `alt` attribute is part of the Page's HTML. It counts only `<img src>` Links, so the `srcset` candidates that `020` also discovers are not counted twice.
- *Consequence:* Resource Issues never change the Health Score, which is defined over Internal Pages (see Open Questions).

### D3. What makes a Rule Issue-type
**In short:** `issue` is reserved for definite defects, because Issue-type Issues alone drive the Health Score; what can be intentional is a `warning`, and improvements are `opportunity`.

There are 10 Issue-type Rules, 6 in v0.1 (`internal-4xx`, `internal-5xx`, `internal-no-response`, `redirect-loop`, `title-missing` and `canonical-to-non-indexable`):

- `internal-4xx`, `internal-5xx`, `internal-no-response` and `redirect-loop`
- `title-missing` and `title-multiple`
- `canonical-to-non-indexable` and `canonical-conflicting`
- `exact-duplicate`
- `image-broken`

A `warning` is anything that can be intentional, or that should not lower the score: noindex, canonicalised, blocked by robots.txt, redirects, missing canonical or H1, and `http-url`. Priorities follow Screaming Frog's where they are known.
- **`http-url`** is a Warning with High Priority. A site served over plain HTTP is flagged prominently, but its Health Score still reflects its other defects.
- *Alternative: copy Screaming Frog's Issue Types everywhere.* Rejected. They are not fully documented, and several are Opportunities that would hide definite defects from the Health Score.
- *Consequence:* changing a Rule's Issue Type later changes Health Scores. It is treated as a contract change and noted in the changelog.

### D4. 42 Rules, 15 of them in v0.1
**In short:** all 42 Rules are kept; v0.1 ships the 15 that ROADMAP lists under "The v0.1 Rules", and the other 27 are v0.2.

The spec marks each requirement and scenario with its release. Noindex and nofollow each combine meta robots and X-Robots-Tag: the problem is the same, and `detail.sources` tells the agent where to fix it. Every Rule has a distinct fix. The low-value Rules (`title-same-as-h1`, `h1-too-long`, `url-underscores`, `url-parameters`, `meta-description-too-short`) are `opportunity`/`low`, so they do not touch the Health Score and sort last in Reports. Each one can be disabled with `enabled = false`.

### D5. When Rules run
**In short:** a running Crawl's Issues are computed live on each read; the post-crawl pass materialises them, after `030`'s link counts, whenever a Crawl ends as `completed` or `stopped`.
- **During the Crawl,** nothing is written. The Issues reader computes the Issues live from the queries (D16), so a running Crawl shows its Issues so far.
- **In the post-crawl passes,** this change's pass materialises them. The pass, `materialise_issues` in `spider.rules.passes`, only orders the store's units: it submits one writer unit per enabled Rule, which deletes the Rule's rows and inserts what its query returns, and then one unit that writes the Health Score. A second run replaces the first. Unlike `020` D14's passes, which are store functions, it lives above the store, since it needs the Rule catalogue.
- **Order.** Through `020`'s hook, the passes run in this order:
  1. `030` link counts
  2. `040` Rules, then the Health Score
- **When they run.** They run for Crawls that end as `completed` or `stopped`, before the final Crawl State is written, and again when a resumed Crawl ends. `failed` and `interrupted` Crawls get the pass only once they are resumed and end, and are read live until then.

### D6. Each Crawl records its Rule configuration
**In short:** when a Crawl starts, its `rules` table records the whole Rule configuration, so the crawl file explains its own Issues.

The table holds every Rule's type, priority, enabled state, effective thresholds, guidance texts and reproducing query.
- *Also in `crawl.config`:* the `[rules.<id>]` settings are part of the resolved settings snapshot that `config` holds and `resume` reads (dumped by Rule id). The `rules` table is the form that Rules and agents read.
- *Why:* crawl files stay self-contained ([ADR-0002](../../../docs/adr/0002-sqlite-crawl-store-public-schema.md)). A resumed Crawl keeps the configuration it started with. A Report built later shows the thresholds that produced its Issues, and the guidance texts are available even to a reader without the same tool version.
- *Alternative: store only the Rule ids and read metadata from the installed tool.* Rejected. The thresholds used would be lost, and texts could silently change.

### D7. `issues` is a view over `affected_urls`
**In short:** `issues` is a view that counts each Rule's rows in `affected_urls`, so no count of Affected URLs is stored.

A count that only repeats the rows of another table is not stored (ADR-0005). The view joins `rules` with the count of each Rule's rows in `affected_urls`, read over the primary key's `rule_id` prefix.
- It cannot disagree with `affected_urls`, and the post-crawl pass has nothing to recount.
- It holds the last pass's result. For a Crawl without a final pass the Issues reader computes the same shape live instead (D16).
- It keeps the name and columns that `050`'s `issues` Command and export and `070`'s Report read, `affected_count` included.
- *Cost:* each read of `issues` counts the rows of `affected_urls`, a scan of its primary key.
- **The first view of the schema.** `018`'s `spider schema` already lists a `kind` of `table` or `view`. This change declares the view in `spider.store.schema`, with the other public tables, next to its description, column descriptions and `values`, and extends `018`'s contract test to views: the file must have the view, with its column names in order. SQLite reports no `NOT NULL` and its own type names for a view's computed columns (`INT` for a `CAST(… AS INTEGER)`), so a view's types and nullability come from the declaration only, and `STRICT` is checked for tables only.
- *Alternative: a real table `issues` with a stored `affected_count`, updated with `affected_urls`.* It stores a count of other rows, and every write and every pass must keep it right. Rejected by ADR-0005.
- *Alternative: no `issues` object in the file,* only `050`'s query. Agents writing SQL would have to know the join. Rejected.

### D8. The Health Score
**In short:** the post-crawl pass stores the Health Score on the crawl row, and one function computes it for any subset of Internal Pages.
- **Formula.** `floor(100 × (N − A) ÷ N)`, and no score when N is 0. Rounding down shows 100 only when no Page has an Issue-type Issue.
- **Counts in SQL, the formula in Python.** `health(connection, rated, affected)` in `spider.store.health` is the one function: it counts N, the Pages among the `url_id` that `rated` selects, and A, those of them among the Affected URLs that `affected` selects, with `COUNT` and `COUNT(DISTINCT)`, and returns them with the score of the pure `health_score(n, a)`. Only Pages are rated, since a Segment selects URLs, and some of them are no Page.
  - **Where it lives.** `spider.store.health` holds the formula, `health` and the pass's unit that writes the score, since the score is a derived column of the crawl row and a count over stored rows.
  - **Who passes what.** The pass rates every Internal Page against the stored Affected URLs. `050`'s Segments and `070`'s Report pass their own `rated`, and take `affected` from `health_affected_in(connection, catalogue)`, which reads the Affected URLs as the Issues reader does: stored for a `completed` or `stopped` Crawl, live otherwise (D16).
  - *Alternative: one function over Python sets of Page and Affected URL ids.* It holds every id of a 500k-Page Crawl in memory, where memory is meant to stay flat. Rejected.
- **Which Issue Types count** comes from the Crawl's `rules` table, never from the installed tool.
- **Storage.** Four derived fields of the one-row `crawl` table: `health_score`, `health_internal_page_count`, `health_affected_page_count` and `health_calculated_at`. Only the pass's last unit writes them, after the Rules' rows, so they stay NULL until it runs, and each description starts with `Derived: ` (ADR-0005). `health_score` has no unit suffix, since a score is not a share, and the counts end in `_count` (ADR-0005 rule 5).
  - *Alternative: a one-row `health_score` table.* ADR-0005 keeps `crawl` the only one-row table. Rejected.
- **The time.** `health_calculated_at` comes from the Crawl's clock, since a unit cannot read the time itself (`017` D7): the composition root passes the writer and the clock of the pass's `PassContext` to the Issues pass, which keeps `spider.store` free of the crawl core.

### D9. Strict configuration through `010`'s settings validation
**In short:** `[rules.<id>]` tables are a third kind of `010`'s settings tables, a table of named tables, checked strictly whenever settings load, so a typo fails loudly instead of quietly changing audit results.

They are part of the settings model, which `010` validates eagerly. They fit neither of `010`'s table kinds, since each Rule has its own thresholds and Rule ids hold `-`: the `rules` table is a model built from the registry, with one field per Rule aliased by its id, each an `extra="forbid"` model of `enabled` and its thresholds, and `010`'s table check, closest-key suggestion and `init` template learn it. A table opts into the third kind with one marker that `spider.workspace.tables` names, so a model of models that does not opt in is refused, and so is a setting of another table whose type holds a table model anywhere, in a list, a union or a mapping. Such a table may hold no required field and no secret: a secret inside a named table would escape the redaction of `crawl.config`. A threshold is an integer from 0 to 2^63-1, SQLite's largest INTEGER, since the Crawl stores the thresholds it used (D6). The `workspace` delta spec gives the template's rule for it. Unknown ids, unknown keys and bad values become `settings_invalid` problems with dotted keys, such as `rules.title-to-long`, and a hint naming the closest known id or key. The cost is that a `spider.toml` written for a newer version, with new Rule ids, fails on an older tool; the message names the unknown id, so the fix is obvious.

The table names are Rule ids. They mirror no flag, so `010`'s flag-mirroring key rule does not apply to them.

### D10. Changing thresholds after a Crawl
**In short:** v0.1 does not recompute stored Issues: a Crawl is judged by the configuration it recorded.

`rules apply` (v0.2, in ROADMAP.md) will recompute Issues from stored data. That works because every condition reads only stored data (D1).

### D11. `spider rules` describes the Workspace, not a Crawl
**In short:** `spider rules` shows what the next Crawl will use.

What an earlier Crawl used is in that Crawl's `rules` table, which `050`'s `issues` output and `spider sql` can show.
- *Alternative: accept `--crawl` and show the recorded snapshot.* Deferred to avoid a second meaning for the same Command.

### D12. Category values are snake_case, Rule ids are kebab-case
**In short:** categories are snake_case because they are stored enumeration values; Rule ids are kebab-case because people type them.

`015` requires enumeration values to match `^[a-z][a-z0-9_]*$`, so the categories are `response_codes`, `meta_descriptions` and so on. `070` maps them to its kebab-case Report Section ids. Rule ids are free text that people type as command arguments and as `spider.toml` table names, where TOML bare keys allow `-`.

### D13. Canonical targets use 030's Indexability
**In short:** `canonical-to-non-indexable` fires when the target's Indexability, as `030` defines it, is non-indexable, not on "any non-200".
- **When the target is a Page,** that is the stored `indexability` of `030`.
- **When the target is not a Page,** `030` stores no Indexability, so the Rule applies steps 1–4 of `030`'s order (robots.txt, 3xx, 4xx, 5xx) to its `urls` row, plus `no_response` for a request that got no response.
- **The detail key is `target_reason`:** its values are `030`'s six `indexability_status` values plus `no_response`. Naming it `indexability_status` would give one name two value sets (ADR-0005 rule 7), because `no_response` is not a value of that column.

A 2xx non-HTML target, such as a PDF, therefore counts as indexable, as it would for `030`. A target that was never requested is not judged.
- *Alternative: store Indexability for every Internal URL.* It would add Indexability columns to `020`'s `urls` table, which the v0.1 schema blueprint does not have. It is left to `030`'s Open Questions.

### D14. The tables under ADR-0005
**In short:** `rules` and `affected_urls` go through `018`'s `public_table()` beside the views, and the store takes a Rule as a structural `RuleQuery`, so it never imports `spider.rules`.

Each table is then `STRICT`, and its enumerations and flags get CHECKs from the declared values. The tables and the views are declared in `spider.store.schema_rules`, on the metadata of the core tables in `spider.store.schema_core`, and `spider.store.schema` gathers both by name, since `create_all` and `spider schema` see only what that metadata holds; `spider.store.issues` holds the Issues reader, `spider.store.issue_units` the units that store the Rules' Affected URLs, and `spider.store.health` the Health Score (D8). `spider.rules` sits above the store as the crawl core does: the store takes a Rule as the `RuleQuery` of `spider.store.rule_queries` (`id` and `reproduce_sql`), which also holds `rule_not_found` and `rule_not_computable`. `affected_urls` is `public_table()`'s first `WITHOUT ROWID` table, so it gains a `without_rowid` keyword.
- **`rules`:** keyed by `id`, the Rule id, as TEXT: a public identifier that a user types (ADR-0005 rule 2). It is an ordinary rowid table: ADR-0005 rule 15 keeps `WITHOUT ROWID` for a natural composite key with narrow rows, and a `rules` row holds the guidance texts and the query.
  - `category`, `issue_type`, `priority` and `applies_to` are enumerations whose values are `Literal`s in `spider.store.records`, as `020`'s are, so the code, the CHECK and `values` cannot disagree.
  - `reproduce_sql` holds the Rule's query (D15).
  - **When it is written:** in the transaction that creates the `crawl` row. This change adds a `rules` field to `015`'s `NewCrawl`, beside `section_crawl`, and `create_crawl` writes its rows. A Crawl that dies before its first unit still records its configuration, which the live path reads.
- **`affected_urls`:** keyed by `(rule_id, url_id)`, `WITHOUT ROWID`, as a table of pairs with narrow rows (rule 15). Both columns are declared references.
  - `affected_urls_url_id` on `url_id`: it serves the Issues of one URL (`050`'s `page <url>`) and the Health Score's count of affected Pages. A query by Rule uses the primary key's prefix and needs no index.
  - `detail` is JSON, nullable: nothing filters on it in v0.1 (rule 11).
- **`issues`:** a view (D7).
- **The `crawl` fields:** D8.

### D15. Reproducing queries
**In short:** every Rule is one SQL query over the public schema that reproduces its Affected URLs, so an agent that reads only the crawl file can check an Issue; the tool runs only its own registry's queries, never a file's.

The query is also the base of v0.3's User SQL Rules.
- **Shape:** a read-only `SELECT` that returns `url_id` and `detail`. It reads the effective thresholds from the Crawl's `rules` row, for example `json_extract((SELECT thresholds FROM rules WHERE id = 'low-word-count'), '$.min_words')`. Its text is then a constant of the Rule: the same in every Workspace and Crawl, and still right under overrides.
- **Only stored columns:** a condition that needs a value the file does not hold needs a column first, which is a schema change (ADR-0005). Every v0.1 Rule finds its data in `urls`, `pages` and `links`.
- **The pass's unit** runs `INSERT INTO affected_urls (rule_id, url_id, detail) SELECT :rule_id, url_id, detail FROM (<query>)`. Each statement is built once per Rule per pass, which costs nothing beside the query, so it is not cached (`017` D9 asks for statements built once of the units written for each URL). The unit reads only the file, so it is deterministic when it runs again (`017` D7).
- **Which SQL runs:** the registry's, which is the tool's own code, for the Rules that the Crawl's `rules` table marks enabled, with the thresholds of that table (read by the query itself). The pass and the live reader never run the `reproduce_sql` text of a file: that would turn a data file into code, since a crafted or shared crawl file's query could `ATTACH` a new database, which writes an arbitrary file, or run pragmas, and there is no SQLite authorizer yet (`050`'s `sql` runs SQL that the user typed, a different trust level).
- **Where it is read:** `rules.reproduce_sql` in the file, and `spider rules list` and `show`.
- **Exclusions are explained in the query:** an agent reads the query, not this design, so a condition that leaves a value out carries an SQL comment with the reason. `internal-no-response` and `image-broken` leave out `fetch_error = 'record_failed'`: the Crawl got a response and failed to record it, which is the tool's failure, reported by `020`'s `record_failed` warning, not the site's.

### D16. Issues of a Crawl without a final pass
**In short:** the Issues reader in `spider.store.issues` reads stored Issues for a `completed` or `stopped` Crawl and computes them live otherwise; it is the one way `050`'s `issues`, `issues <rule-id>`, `summary` and `page <url>` read Issues.
- **Which path:** the Crawl State is the marker because `020` writes `completed` and `stopped` only after the post-crawl passes, in the unit that ends the Crawl, so they imply a finished pass over the current rows.
  - A resume sets `running` first, so its Crawl is read live at once, without clearing anything.
  - A process killed during the pass leaves `running`, which `060` records as `interrupted`, and that is read live.
  - `failed` gets no pass from `020`, and is read live.
  - *Alternative: a `Derived: ` column such as `issues_materialised_at`.* A resume would have to clear it in the unit that sets `running`, and it could disagree with the Crawl State. Rejected: the state already says it.
- **The live path** runs each enabled Rule's query on a read-only connection, as one read, and returns the shape of the `issues` view, or of `affected_urls` for one Rule or one URL. `affected_urls` is ignored, because after a resume it holds the previous pass's rows.
- **Cost:** live Issues cost one evaluation of every Rule per read, on rows that are still growing. `026`'s run of about 500k URLs measures the latency of a full live list during a Crawl and its effect on WAL checkpoints, because a long read holds the WAL from being reset. If the full list takes more than 30 seconds at 500k URLs, the design is revisited: per-Rule reads, or materialising at intervals. The same run measures `page <url>`, which runs every Rule's query for one URL: over 1 second at 500k URLs, the reader gets per-URL forms of the queries.
- **Interface:** `issues_in(connection, catalogue)` and `affected_urls_in(connection, rule_id, catalogue)` take an open `reading()` connection and return Core selects: in the shape of the `issues` view, and of `affected_urls` for one Rule (`url_id`, and `detail` as stored JSON text). A Command opens one `reading()` and runs every select of its invocation there, so it reads one snapshot, and it joins, filters, orders and pages them in SQL (`050` D4, D14). Both paths check a rule id against the Crawl's own `rules` table, and `rule_not_found` lists the closest ids of that table in `details.suggestions`. On the live path, a Rule that the file records but this tool's catalogue lacks is `rule_not_found` too, since this tool never runs a file's SQL itself; its message and hint say so. `read_issues`, `read_affected_urls` and `read_url_issues` are the file-level forms, one `reading()` each.
- **Interface points:** `050`'s Commands call the reader and never query `affected_urls` themselves, so both paths give them one shape. `080`'s documentation tells agents that Issues of a running Crawl are computed on each read and cost more than those of a finished Crawl, and that `affected_urls` and `issues` in the file hold the last pass's result, valid when `crawl.state` is `completed` or `stopped`.

### D17. Codes
**In short:** this change declares one code, `rule_not_found` (exit 4); `settings_invalid` comes from `010` and the `record_failed` warning from `020`.

Declared as `DiagnosticCode` constants in `spider.output.codes`, as `020` D17 does, by the slice that first raises them:
- error, exit 4: `rule_not_found` (`spider rules show` with an unknown id, and the Issues reader with a rule id that the Crawl's `rules` table lacks, or on the live path this tool's catalogue lacks), under `010`'s rule that a code ending in `_not_found` maps to 4

`settings_invalid` (exit 3) comes from `010`, and the `record_failed` warning that the Rule queries leave out is `020`'s.

### D18. Command groups
**In short:** `spider rules` is the first Command group: its Commands are registered and listed under it, its bare form runs `list`, and options are taken only after the Command name.

`spider rules list` and `spider rules show` are the first Commands below a group, while `010`'s CLI registers only top-level Commands. This change adds groups in general: a group's Commands are registered under it, each with its own `@command_meta`, `spider commands` lists each by its full path, as cli-contract names them (`rules list`), and `--help` shows them. A group with no arguments runs its default Command (`spider rules` runs `spider rules list`), and an option given after the group name and before the Command name, other than `--help`, is a `usage_error` whose hint says to put it after the Command name, as cli-contract already asks for a global flag given before the Command name. The mechanism is generic: `060`'s `crawls list|show|rm` inherits it, its default Command and its hint included.

### D19. Populations are views
**In short:** each population is a view of the crawl file, and a Rule's query selects from the view of its own.
- `internal_urls`, `analysed_pages` and `indexable_pages` are public views of the one column `url_id`, declared in `spider.store.schema` beside `issues`: a population is a set of URLs, and a Rule joins its view to the tables it reads. A population is then defined once for some 30 Page Rules, and one test checks every Rule's Affected URLs against its view.
- `reproduce_sql` stays self-contained, since every crawl file holds the views.
- A Rule declares `population`, the name of its view, and `applies_to` is derived from it: `analysed_pages` and `indexable_pages` both give `internal_pages`, since the spec's enumeration names no Indexable population. The Health Score counts every `pages` row instead (D8).
- *Alternative: each query joins its population itself.* Every Page Rule repeats the `parsed` = 1 join, and every Indexable-only Rule adds another, so a wrong copy shows only in that Rule's own tests. Rejected.
- *Alternative: `applies_to` takes the view names.* The stored `applies_to` would then take values the spec's enumeration lacks, and split `internal_pages` in two. Rejected.
- *Alternative: views with every column of `urls` or `pages`.* A Rule would read its view alone, but each column would stand in the public schema two or three times, and so would every later `pages` column. Rejected.

## Test seams

The seams come from [docs/testing.md](../../../docs/testing.md). No new seam is introduced:

- **Seam 4, pure-logic modules.**
  - The Health Score function, with table-driven cases.
- **Seam 2, services and store API.**
  - Every catalogue scenario is tested here: rows written through the store's writers into a real crawl store in a temporary Workspace, then the Rule's query, run by the evaluation entry point; fires or not, with the literal `detail`, out. Test-data builders for `urls`, `pages` and `links` rows are builders, not test doubles.
  - The post-crawl pass is called directly, twice, to test idempotency. "Later edits do not change a completed Crawl" is tested at seam 3+6 instead: after a `spider.toml` edit, the store reader that `050`'s Commands call gives the Crawl's Issues and Health Score as before.
  - The Issues reader's two paths, on crawl files in each Crawl State.
  - The store units are checked with `017`'s `replay_now(writer)`, which makes the writer run them again.
- **Seam 3+6, fixture site plus store contract.** End-to-end slices crawl fixture pages under `/rules/` and read `rules`, `issues`, `affected_urls` and the `crawl` row through the documented tables, read-only. One of them runs every Rule's reproducing query against the stored rows, and one compares the live and materialised paths (D16). `http-url` is a Warning, so the plain-HTTP fixture site does not lower the Health Score in these slices.
- **Seam 6, store contract.** `spider schema` is compared with hand-written `values` lists, keys and indexes, and `018`'s contract test covers the new tables and the view.
- **Seam 1, CLI.** This covers `spider rules list` and `show`, the `settings_invalid` and `rule_not_found` errors and their exit codes, and one real subprocess run whose piped stdout is the in-process output byte for byte.
- **Boundary doubles.** Only the injectable clock, for `health_calculated_at`. Our own modules are never mocked.

## Risks / Trade-offs

- [An `http`-only site gets `http-url` on every Page] → It is a Warning/High, so it tops the Warnings in Reports without lowering the Health Score (D3). The guidance explains the fix.
- [Broken internal images are reported by both `internal-4xx` and `image-broken`] → Accepted, as in Screaming Frog. One is about the URL and one about its use as an image. The fixes point to the same file.
- [Resource and non-Page URL Issues, such as no response or blocked, do not lower the Health Score] → This follows the glossary definition, which is Page-centric. It is documented, and listed under Open Questions.
- [`indexable_pages` holds every analysed Page until `030` stores Indexability] → `title-duplicate` compares non-indexable Pages too until then. `test_non_indexable_pages_are_not_compared` is expected to fail only while `PageRow` has no `indexability` field: once `030` adds it, the test runs, and fails the suite until the view is narrowed.
- [`pages` has no `title_1_width_px` before v0.2] → "Title too long by characters" is tested without it; the v0.1 query reads characters only.
- [Tests named after no scenario] → In `tests/rules/test_populations.py`: `test_a_rule_s_affected_urls_are_members_of_its_population`, every Rule over rows outside each population (D19); in `tests/rules/test_pass.py`: `test_a_rule_query_with_a_colon_is_run_as_written`, since `text()` reads `:name` as a parameter even in a comment or a string; in `tests/rules/test_issues.py`: `test_a_crawl_stopped_by_the_url_limit_lists_its_issues_as_stored`, since the reader takes a stopped Crawl as materialised; in `tests/cli/test_rules.py`: `test_every_rule_applies_to_its_population`, the population the Health Score reads for each Rule; in `tests/rules/test_meta_descriptions.py`: `test_an_empty_meta_description_counts_as_missing`, since the Rule table fires on an empty `meta_description_1` too; in `tests/rules/test_response_codes.py`: `test_a_url_that_robots_txt_kept_from_being_requested_is_blocked`, since `internal-blocked-by-robots-txt` fires whether or not the URL was fetched.
- [Duplicate grouping on about 500k Pages] → A window count over `title_1`, which SQLite computes by sorting, O(n log n), with no extra index. The passes run once per Crawl end.
- [Each read of `issues` counts `affected_urls`] → A scan of its primary key, which a Crawl of about 500k URLs keeps to a few million narrow rows. `050` reads it once per Command.
- [Live Issues of a running Crawl of about 500k URLs are slow, or hold back WAL checkpoints] → `026`'s 500k run measures both. Over 30 seconds for the full list, the design is revisited; over 1 second for `page <url>`, the queries get per-URL forms (D16).
- [`url-uppercase` (v0.2) names Unicode category Lu, which portable SQL cannot test: SQLite's `upper()` and `lower()` change ASCII letters only unless it is built with ICU, and a Rule's query uses no function of ours] → Its definition is settled with the v0.2 URL Rules, over `030`'s `url_path` and `url_query`. A candidate: A–Z plus GLOB ranges of Latin-1, Greek and Cyrillic capitals, skipping A–F inside `%XX` escapes. Ranges on letters work only on those two columns: `020`'s normalisation percent-encodes every non-ASCII character as UTF-8 (`café` becomes `caf%C3%A9`), so `urls.url` and `url_encoded_address` hold Cyrillic capitals only as escapes, while `030`'s `address`, from which `url_path` and `url_query` are cut, decodes the escapes of non-ASCII characters and keeps ASCII escapes encoded.
- [A Rule cannot be written over the stored columns] → It needs a column first, a schema change; the v0.1 Rules need none (D15).
- [Tests of the rules Command group and the registry named after no scenario, which the scenario count ignores] → In `tests/cli/test_rules.py`: `test_the_bare_group_lists_the_rules` (bare `spider rules` runs `list`, as the List Rules requirement says); `test_an_option_after_the_group_name_says_where_it_goes`, `test_an_option_before_a_grouped_command_names_that_command` and `test_a_root_option_after_a_group_name_gets_the_root_hint` (an option is taken after the Command name only, and its hint names where it goes, D18); `test_the_root_help_lists_the_group` (a hidden group fails it); `test_the_group_help_lists_its_commands` (`--help` refused as an option before the Command name fails it). In `tests/cli/test_commands.py`: `test_a_command_in_a_group_is_listed_by_its_full_path` (cli-contract names a Command by its full path, D18); `test_rule_codes_are_self_described` (`rule_not_found` declared outside the list of codes fails it). In `tests/cli/test_global_flags.py`: `test_a_global_flag_between_a_group_and_its_command` (D18). In `tests/cli/test_command_meta.py`: `test_a_command_named_outside_its_group_is_refused`, `test_a_group_whose_default_is_not_one_of_its_commands_is_refused`, `test_a_group_name_with_a_space_is_refused`, `test_a_top_level_command_name_with_a_space_is_refused` and `test_a_group_name_already_taken_is_refused` (Typer keeps the last of two entries of one name, so a taken name must be refused). In `tests/rules/test_registry.py`: `test_the_catalogue_keeps_the_category_order_and_unique_ids` (categories out of order, or two Rules with one id, fail it, since the settings model is keyed by Rule id, D9); `test_thresholds_have_unique_names_and_defaults_of_at_least_0` (a default of -1, or two thresholds of one name, fail it, since the settings model builds a table from them, D9). "Windows console output" sets no console code page, since a Rule's texts are ASCII, so `010`'s Cyrillic tests in `tests/cli/test_encoding.py` stay the guard of the encoding itself.
- [Tests of the Rule settings named after no scenario, which the scenario count ignores] → In `tests/workspace/test_tables.py`: `test_a_table_of_named_tables_follows_the_rules`, with a table without a docstring and one whose named table allows extra keys among the refused ones; the refused tables `UnmarkedNamedTables`, `RequiredNamedTables`, `SecretNamedTables`, `LooseOuterNamedTables`, `ListedTables`, `OptionalTable` and `MappedTables` (a table of named tables is detected by its marker, not its shape, holds no required field and no secret, and no list, union or mapping of a table is accepted, D9). In `tests/cli/test_init.py`: `test_a_table_of_named_tables_in_the_template`. In `tests/cli/test_crawl.py`: `test_a_rule_setting_is_recorded_by_its_rule_id`, since `crawl.config` records every settings table (D6). In `tests/cli/test_rules.py`: `test_a_misspelt_threshold_gets_the_closest_name` (the suggestion looks a Rule table up by its id, not its field name, which failed with internal_error); `test_a_rule_setting_of_another_type_is_invalid` (`"70"` and `"no"` are not read as a number and a boolean); `test_the_rules_of_another_workspace` (`--workspace` is honoured); `test_a_threshold_above_the_integer_range_of_the_store_is_invalid` (a value beyond SQLite's INTEGER is `settings_invalid`, neither accepted nor an internal_error); `test_a_rule_id_in_capitals_gets_the_closest_id` (it gets a hint); `test_a_rule_table_named_by_its_field_name_is_invalid` (Rule tables are read by id only, not `validate_by_name`). In `tests/workspace/test_settings.py`: `test_a_key_that_cannot_be_followed_keeps_the_hint_of_the_next` (the closest-key walk that meets a list of tables gives a hint, not an AttributeError's internal_error); `test_template_loads_as_defaults` runs over the tool's tables and the fixture app's, so a named-table header written uncommented fails it. "Disabled Rule is listed" asserts the whole set of Rules that are off, so `enabled` false by default fails it. The rules tests run in a temporary Workspace (`pytestmark`), never in the folder pytest starts in.
- [Tests of the schema's views named after no scenario, which the scenario count ignores] → In `tests/contract/test_schema.py`: `test_a_new_file_has_the_declared_views` (D7: the file has each declared view, with its columns in order); in `tests/contract/test_conventions.py`: `test_references_name_a_listed_column` (a view's declared reference to `rule.id` fails it), since a view's references are written by hand; in `tests/contract/test_rules.py`: `test_a_view_that_declares_other_columns_than_its_query_is_refused` (a check made only after `CreateView` has added the view to the metadata fails it).
- [Tests of the Issues pass named after no scenario] → In `tests/rules/test_pass.py`: `test_the_units_of_the_issues_pass_run_again_the_same`, through `017`'s `replay_now` (a unit without its DELETE fails it); `test_the_issues_pass_comes_last` (a pass listed after it fails it), since `030`'s link-count pass must run first (D5); `test_a_rule_query_ending_in_a_comment_is_run_as_written` (a trailing comment that swallows the subquery's closing parenthesis gives incomplete input).
- [Tests of the Issues reader named after no scenario, which the scenario count ignores] → In `tests/store/test_reading.py`: `test_a_read_sees_one_snapshot` (each SELECT of a read seeing the file as it is then fails it). In `tests/rules/test_reader.py`: `test_a_disabled_rule_has_no_affected_urls_read_live`, since the live path runs only the enabled Rules' queries (D16), and the live Issues of one URL leave out a disabled Rule too; `test_an_unknown_rule_id_is_rule_not_found` (not a StopIteration); `test_issues_of_a_rule_the_catalogue_lacks_come_after_its_own` (the stored path keeps them); `test_the_affected_urls_of_a_rule_the_catalogue_lacks_are_read_as_stored` (not rule_not_found for a Rule the file holds); `test_an_issue_and_its_affected_urls_are_read_from_one_snapshot` (through `issues_in`); `test_an_unknown_rule_id_gets_the_closest_ids_the_crawl_records` (the id misspells a Rule that only the file records, so suggestions from the catalogue would fail it); `test_a_rule_this_tool_lacks_is_not_read_live` (not "No Rule has the id" for a Rule the file has). In `tests/cli/test_rules.py`: `test_an_unknown_rule_id_gets_the_closest_ids` (it gets suggestions). "Live and materialised Issues agree" is `test_live_and_materialised_issues_agree` in `tests/rules/test_issues.py`: one test over both adapters, `StoredIssues` and `LiveIssues`, on the same crawl file.
- [A read holds one snapshot of the file until it ends, so a reader that keeps `reading()` open for long keeps WAL checkpoints from completing] → Every read is one operation that ends at once; `060`'s status loops must open a new read each time. `026`'s run of about 500k URLs measures live reads during a Crawl (D16).
- [A read of a rollback-journal file is not one snapshot] → In that mode a read transaction's SHARED lock holds the writer's commit until the read ends, and a read of every Rule's query could pass the writer's 30 s busy limit and end the Crawl with `write_failed`; so `reading()` begins a transaction in WAL mode only, and the statements of a read of a file on a network share each see the file as it is then (`test_a_read_of_a_rollback_journal_file_lets_the_writer_commit`).
- [The writer's closing checkpoint waits for open reads, at most `WRITER_BUSY_SECONDS` (30 s)] → A read ends in far less, so the close waits only as long as the reads open then; a read held longer leaves the WAL until the next read-write open, since a read-only connection never checkpoints, and a copy of the file made meanwhile lacks those commits (ADR-0002's self-contained file). A shorter bound, such as 1 s, is rejected for that reason (`test_closing_waits_for_an_open_read_and_leaves_no_wal`).
- [One Rule query that fails, such as on a file of an older schema, fails every live read] → Migrations, from v0.1, and `060`'s handling of older files own it.
- [Tests of the slice's Rules named after no scenario] → In `tests/rules/test_headings.py`: `test_an_empty_h1_counts_as_missing`, since the Heading Rules table fires `h1-missing` on an empty first h1 too, and only "Missing H1" has a scenario. In `tests/rules/test_response_codes.py`: `test_an_internal_url_outside_the_scope_is_an_internal_url` (`in_scope = 1` in `internal-4xx`'s query fails it), since `internal_urls` includes the Internal URLs that a Section Crawl requests outside its folder (D2). "A Rule's query returns its stored Affected URLs" and "Live and materialised Issues agree" cover all five slice Rules (`RULE_PAGES` without its links to `/rules/down` and `/rules/reset` fails them).
- [On the live path, a Rule that the file records but this tool's catalogue lacks, as in a running Crawl of a later tool, cannot be read] → It is `rule_not_found`, whose message says that this version cannot compute it live and whose hint names `spider sql` with the Rule's `reproduce_sql`, since the tool never runs a file's SQL itself (D15).
- [An Internal URL that answers with a status outside every Rule's range, 1xx or 600 and above, raises no Issue] → `internal-4xx` and `internal-5xx` read 400–499 and 500–599, and `internal-no-response` reads requests without an HTTP response. Whether `internal-5xx` becomes 500 and above, or a Rule for other statuses is added, is decided with the rest of the v0.1 response code Rules.
- [A Crawl resumed after a tool upgrade that changed a Rule's SQL materialises with the new SQL, while its `rules.reproduce_sql` holds the old] → The pass runs the registry's SQL (D15). `060` (`resume`) owns the case and decides whether to refuse, warn, or rewrite the `rules` row.
- [The Purpose of `openspec/specs/workspace/spec.md` says that the keyed table `groups` stands in for `040`'s `[rules.<id>]`, which is a table of named tables (D9)] → A delta spec cannot change a Purpose, so the archive of this change rewords it: `groups` stands in for keyed tables, whose entries the user names, and `[rules.<id>]` is the third kind, a table of named tables.
- [Some Priorities differ from Screaming Frog's] → The documented principle (D3) applies, and `docs/rules.md` lists every Rule's type and priority.
- [Tests of the Health Score named after no scenario] → In `tests/rules/test_health_counts.py`: `test_a_disabled_rule_does_not_lower_the_live_score`, since a disabled Rule stores no Affected URLs and the live score must agree with the stored one (D16); `test_a_finished_crawl_is_scored_from_its_stored_issues`, since `health_affected_in` reads a Crawl as the Issues reader does (D16); `test_a_page_too_large_to_parse_is_still_rated`, since N counts every `pages` row, not only the analysed Pages that the Page Rules read.
- [No reachable row lies outside a Page population with Page data] → A Page that was not parsed holds NULL Page data, and `PAGE_DATA` is the one Page data extractor, so an `extractor_error` leaves the columns NULL too. A Rule's join to `analysed_pages` is therefore checked by the view's own assertion in `test_a_page_that_was_not_parsed_is_not_analysed`, the population test catches a Rule that takes a NULL as missing, and `indexable_pages`' join waits for `test_non_indexable_pages_are_not_compared`, which runs once Pages record Indexability. `test_a_failed_extractor_raises_no_issue_for_its_missing_columns` fills the title columns of a Page with an `extractor_error`: it stands for a later extractor that fails beside `PAGE_DATA`.
- [A Page's live Issues run each window Rule over every Page] → On a running Crawl, `url_issues(url_id)` runs each enabled Rule's whole query and filters it by `url_id` outside, which SQLite cannot push into a window such as `title-duplicate`'s, so `spider page <url>` sorts all Pages once per window Rule (D16). Bounded and accepted below 300 ms a call: on a crawl file of 100k Pages, one call takes about 115 ms (the median of three runs on a developer laptop). A per-URL form of a window Rule would give each Rule a second form, against D1.
- [Tests of the configured-Rule projection named after no scenario] → In `tests/cli/test_rules.py`: `test_show_gives_the_fields_of_a_list_item`, from the requirement "Show one Rule" (the same fields as a list item): it fails when a field is projected into the item but not listed in `RULE_FIELDS`, which `spider rules list` would then drop.
- [A crawl file of a later tool, read live by this tool] → A Rule that the file records but this tool's catalogue lacks counts in the stored Health Score and Issues, but not in the live ones, since this tool cannot compute its query. The live reader shows what this tool can compute; the stored score of a `completed` or `stopped` Crawl is the file's own.
- [`TITLE_MULTIPLE` in `tests/support/rules.py` is a later tool's Rule] → The Health Score tests record `title-multiple`, with its spec condition, as a crawl file of a later tool would, since no two Issue-type Rules of this tool fire on one Page yet. Once the catalogue registers `title-multiple`, those tests take the registered Rule and the later tool's row goes.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds `rules`, `affected_urls`, the `issues` view and the four `health_*` fields of `crawl` to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5).

## Open Questions

These can be answered later without changing this change's specs or tasks:

1. **Resource Issues and the Health Score.** Should Resource Issues count against the Health Score, by attributing each one to the Pages that reference the Resource?
2. **Overriding Issue Type and Priority.** Should `spider.toml` be able to change a Rule's Issue Type or Priority, and if so, how do Health Scores stay comparable?
3. **Which redirects `internal-3xx` reports.** Should it report only redirecting URLs that are linked from Pages, or also intermediate hops reached only through other redirects?
4. **Case-insensitive duplicates.** Should duplicate comparisons (titles, meta descriptions, H1) ignore case?
5. **Does the pass need the `[rules.<id>]` settings when the Crawl ends?** Recommended: no, so `020`'s `PassContext` carries no settings. Which Rules are enabled, and their effective thresholds, come from the Crawl's own `rules` table, recorded when the Crawl was created (D6): the pass runs a unit per Rule that the table marks enabled, and each query reads its thresholds from its `rules` row (D15). Reading the current `spider.toml` at the end would let an edit made during the Crawl, or before a resume, change Issues that the recorded configuration decides, against D6 and D10, and "Later edits do not change a completed Crawl".
6. **Running a file's recorded queries (v0.2).** The pass and the live reader could run a Crawl's own `reproduce_sql` under a SQLite authorizer that allows only reads (no `ATTACH`, no pragmas), so a resumed Crawl keeps the queries it recorded.
