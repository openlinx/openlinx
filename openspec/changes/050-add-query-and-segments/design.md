> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for motivation. This change adds no tables. It reads what other changes write:

- **`010-add-workspace-and-cli-contract`**: Workspace and `spider.toml` loading with its settings check, and the output contract. That contract covers the formats `json|jsonl|table`, the output layer `spider.output`, the paging envelope with `--fields` and opaque cursors, the global flags, diagnostics, exit codes and `spider commands`. 010 is archived before this change starts.

This change adds to that contract the `csv` format, the CSV policy, `--no-bom` and `-o` (D12, D13). They moved here from 010 by the maintainer's decision of 2026-10-01, and `specs/cli-contract/spec.md` holds their requirements.
- **`015-add-crawl-store`** and **`018-add-schema-conventions`**: the SQLAlchemy Core table objects, read-only connections, the `--crawl` option and crawl metadata (`crawl.completed_at` and `crawl.state`). Every table is `STRICT`, so reading a crawl file needs SQLite 3.37 or later (ADR-0005).
- **`020-add-crawl-core`**: the `urls` table (`fetch_state`, `skip_reason`, `blocked_by_robots_txt`, `fetch_error` with `record_failed`, `crawl_depth`, `response_time_ms`), `stop_reason` with its six values, the Link types, and URL normalisation, which `page <url>` reuses. **`022-add-fetch-policy`**: Redirect Chain hops (`redirect_url_id`), the `response_headers` table and Resource checks.
- **`030-add-page-data`**: `pages` (96 columns, with the unique index `pages_address` as its only secondary index), `links` and `page_sources`. The inlink columns are derived and NULL until the post-crawl pass.
- **`040-add-rules`**: the Issues reader in `spider.store.issues`, the per-Crawl `rules` table with `reproduce_sql`, the `issues` view with its computed `affected_count`, `affected_urls`, the derived `health_*` fields of `crawl`, and the Health Score function.
- **`060-add-crawl-control`**: the Crawl State `interrupted`, and `status`, whose counts come from the heartbeat's progress counters (D17).

All query logic lives in the **Query Service** (`src/spider/services/query.py` plus `src/spider/query/`). The CLI modules only parse flags and serialise, and `090-add-mcp-server` wraps the same service calls.

The scenarios use the column names that 030 publishes (`address`, `status_code`, `title_1`, `title_1_length`, `meta_description_1`, `word_count`, `crawl_depth`, `unique_inlinks`, `indexability`, `indexability_status`), the table names `pages`, `links`, `urls`, `issues` and `affected_urls`, and rule ids from 040's catalogue (`title-missing`, `title-too-long`, `h1-missing`, `meta-description-too-long`, `image-broken`). The summary's `crawl.completed_at` is `015`'s `crawl.completed_at`. Rule ids in the scenarios come from `040`'s 42-Rule catalogue; v0.1 ships 15 of them, and a scenario's stored Issues need not be ones v0.1 evaluates.

## Goals / Non-Goals

**Goals:**
- Stable, documented JSON contracts: the summary model (shared with 070), the `--where` grammar (shared with Segments, 070, 080 and 090), and the item shapes of `pages`, `page`, `issues` and `export`.
- Every query stays in SQLite. Filtering, sorting, paging and Segment membership are compiled to SQL, so memory stays flat at 500k Pages.
- Crawled text never becomes SQL or code: `--where` is parsed and compiled, and `sql` is sandboxed.

**Non-Goals:**
- A general SQL dialect in `--where` (that is what `sql` is for), joins across views, and column-to-column comparisons (see Open Questions).
- Storing Segment membership, or caching query results between invocations.
- Output mechanics that 010 owns: the formats `json`, `jsonl` and `table`, the paging envelope and diagnostics.
- MCP tool definitions (090) and HTML rendering (070).

## Decisions

### D1. A hand-written parser for `--where`, compiled to SQLAlchemy Core
A small tokenizer and a recursive-descent parser produce an AST. A compiler turns the AST into a Core expression against the chosen view's table object, binding every literal as a parameter. Column names resolve only against that table's known columns (ADR-0003), and unknown names get `difflib` close matches in `details.suggestions`. Nesting depth is capped at 64.
- *Alternatives:* Lark or pyparsing add a dependency and give weaker control over error positions. Accepting SQL fragments checked by sqlglot is a heavy dependency, leaves room for injection mistakes, and brings SQL dialect surprises. JMESPath is unfamiliar for tabular filters.

### D2. Two-valued logic for nulls
Every predicate except `is [not] null` compiles to `(col IS NOT NULL AND <predicate>)`, so a predicate on a null value is false and `not` makes it true.
- *Alternative:* plain SQL three-valued logic, where `not (word_count >= 300)` silently drops null rows. That surprises agents and people alike.

### D3. Regex and case-folded `contains` as SQLite functions
Every read connection that the Query Service opens registers two deterministic functions:
- `spider_regexp(pattern, value)`: Python `re.search`, with compiled patterns in an LRU cache.
- `spider_contains(value, needle)`: `needle.casefold() in value.casefold()`.

Values are passed as `CAST(col AS TEXT)`, so `status_code ~ '^4'` works. Patterns are compiled at parse time, so a bad pattern fails as `invalid_where` before any query runs.
- *Alternatives:* SQLite `LIKE` folds case only for ASCII, which is wrong for Cyrillic titles. The ICU extension is not available in every Python build. Filtering in Python after fetching would break paging and streaming.

### D4. Keyset paging inside 010's opaque cursor
The sort keys, followed by `address` as the tie-breaker, form the keyset. The cursor payload is the last row's key values. 010's cursor rule binds the cursor to the Command, its arguments and its filters, and this change passes the Crawl, `--where`, `--sort` and `--segment` to that binding. "Nulls last" is compiled as `(col IS NULL), col` for each key, which avoids relying on the SQLite version for `NULLS LAST`.
- *Alternative:* OFFSET paging. Walking 500k rows costs O(n²), and rows shift or repeat while the Crawl is still writing.

### D5. Segments are a `[segments]` table, checked at load time and compiled to one CASE expression
- **Order:** `[segments]` in `spider.toml` is read in document order, because `tomllib` and pydantic-settings keep insertion order.
- **Check at load time:** this change registers a validator for `[segments]` in 010's settings model. The validator checks each name and compiles each expression against the static Core definition of the `pages` table. That needs no crawl file, so it runs whenever settings load and reports through 010's `settings_invalid`, with `details.errors[].key` `segments.<name>`.
- **Membership:** at query time the Segments compile to `CASE WHEN e1 THEN 'n1' WHEN e2 THEN 'n2' … END`, which gives first-match semantics for free, and `--segment X` becomes `WHERE <case> = :x`. `summary` needs membership for many aggregates, so it materialises the CASE once into a connection-local `TEMP` table of (page key, segment). The main database file is still never written.
- *Alternatives:*
  - A `[[segments]]` array of tables, whose order TOML guarantees, is more verbose for the common case. It was rejected, and the ordering risk is noted below.
  - Checking Segments lazily, only in the Commands that use them, lets a broken definition go unnoticed. It was rejected in the cross-change review (G6).
  - Membership stored at crawl time would need a re-crawl or a write to the store, which contradicts "applied at query time".

### D6. The summary model as msgspec Structs
One set of `msgspec.Struct` classes (`SummaryModel`, `CrawlInfo`, `StatusClasses`, …) defines the member names, types and order of the summary JSON. `070-add-html-report` imports the same classes, so the two cannot drift. `docs/contracts/summary.md` documents every member. The contract test compares the output with a hand-written expected JSON for the fixture site, and never with a generated snapshot.
- *Alternative:* ad-hoc dicts built separately in the CLI, the MCP server and the Report.

### D7. Health Score comes from 040
The summary's `{score, internal_pages, affected_pages}` follows the Crawl State, as `040`'s Issues do (D14):
- **`completed` or `stopped`:** the derived fields that `040`'s pass wrote on the `crawl` row: `health_score` → `score`, `health_internal_page_count` → `internal_pages`, `health_affected_page_count` → `affected_pages`. Nothing is recomputed, so the summary agrees with the file.
- **Any other state:** `040`'s Health Score function, over all Internal Pages and the Affected URLs of *Issue*-type Rules that the reader computes live. A `running` Crawl gets a partial score at once.
- **A Segment** (v0.2) always uses the function, over the Segment's Pages and the reader's Affected URLs, materialised or live. It never re-implements the formula, and an empty population gives `null`.
- *Alternative: always compute at query time,* as the draft had. It repeats `040`'s work on every call and could disagree with the stored fields that agents read with `sql`. Rejected.

### D8. Response-time statistics
The count, min, max and mean come from SQL aggregates, and the histogram from a `CASE` bucketing query. The four nearest-rank percentiles come from one sorted read: a `row_number() OVER (ORDER BY response_time_ms)` query over the population that keeps the rows at the four ranks. `urls.response_time_ms` has no index (`020` D18, ruling Q3), so this is the one sort the summary pays.
- *Alternative:* one `ORDER BY … LIMIT 1 OFFSET rank-1` query per percentile, as the draft had: four sorts of up to 500k rows.
- *Alternative:* numpy percentiles interpolate, so they report values that were never observed and don't match the spec's nearest-rank definition.

### D9. `sql` sandbox in three layers
1. **Statement check:** exactly one complete statement, whose first keyword after comments is `SELECT` or `WITH`. Python's `sqlite3` also refuses multiple statements.
2. **Authorizer allowlist on 015's read-only connection:** `SQLITE_SELECT`, `SQLITE_READ`, `SQLITE_RECURSIVE` and `SQLITE_FUNCTION`, except `load_extension`. Everything else is denied and reported as `sql_not_allowed`.
3. **Progress handler:** aborts after `--timeout` seconds and reports `sql_timeout`.

Rows are read with `fetchmany(limit + 1)` to set `truncated`, and BLOBs are mapped to `{"blob_bytes": n}`. For "no such column" and "no such table" errors, `details.suggestions` takes close matches from the schema metadata.
- *Alternatives:* `mode=ro` alone still allows ATTACH and PRAGMA, which change connection state. Fully parsing SQL with sqlglot is heavy.

### D10. Export streams rows through the output layer's serialisers
One read transaction iterates the view's rows with `fetchmany(1000)` and hands each row to the row serialisers of `spider.output`: 010's NDJSON for `jsonl`, and the CSV writer of D12 for `csv`. Each row is written as soon as it is read, to `sys.stdout.buffer` or to the `-o` target of D13: the file receives exactly the stdout bytes, it is replaced only on success, and a locked target is reported as `output_not_writable`.

The `resources` view is one SQL query:
- the `urls` rows that are targets of `image`, `css`, `javascript`, `video`, `audio` or `media` Links and have no `pages` row
- `type` from the first such Link, by source row and `ordinal`
- `inlinks` from a count over `links`
- *Alternatives:* pandas `to_csv` is a dependency and holds the data in memory. A second CSV writer for `export` would duplicate the policy of D12 (G5).

### D11. Output and error details local to query Commands
- `page --html` (v0.2) adds `html` (the `page_sources` bytes decoded with their `encoding`) and `encoding` to the normal JSON, as G4 decided. `--headers` adds `headers` the same way, so agents get everything in one call and both flags combine.
- The default `pages` fields are six compact columns, for token economy.
- The default order of `issues <rule-id>` is by Unique Inlinks, descending, which matches the Report's top-N tables. The Report and the Command then show the same "most important first" Affected URLs. `unique_inlinks` is derived, so it is NULL until `030`'s post-crawl pass, and a `running` Crawl's Affected URLs come in `url` order.
- The codes defined here, their exit-code classes, and `details.suggestions` / `details.accepted` are listed in the spec. The diagnostic shape, the exit-code table and the codes `usage_error`, `invalid_value`, `invalid_cursor`, `unknown_field` and `settings_invalid` are 010's. `output_not_writable` and `output_written` belong to this change's `cli-contract` spec, and `rule_not_found` is 040's.

### D12. The CSV policy

Moved here from 010's D4, together with the `csv` format, by the maintainer's decision of 2026-10-01. The writer lives in 010's output layer `spider.output`, so 010's lint guard on `sys.stdout` still holds, and every CSV output goes through it.

- **How rows are written:** `csv.writer` over `io.StringIO(newline="")` with `lineterminator="\r\n"`. The text is encoded as UTF-8, and `﻿` goes first unless `--no-bom` is given.
  - The byte-order mark makes Excel read UTF-8 correctly, which matters to the people who read exports and Report CSV files.
  - CSV parsers used by agents skip the mark or accept `--no-bom`.
- **Cell rules:**
  - Nested values become compact JSON, and null becomes an empty cell.
  - Numbers are written unchanged, so negative numbers stay numbers.
  - Text that starts with `=`, `+`, `-`, `@`, `\t` or `\r` gets a leading `'`. This is the OWASP guidance on CSV injection, and crawled text is untrusted.
- **One implementation for everyone:** this change's `export` and `070`'s Report CSV files call the same writer, and neither redefines the policy (G5).
- **Alternative:** no byte-order mark by default. Rejected by G5, because Excel users open these files directly.

### D13. `-o` replaces the target atomically

Moved from the `-o` bullet of 010's D3. 010's `Output` object holds the optional `-o` target, and `OutputOpt` and `NoBomOpt` are global flag types next to 010's `WorkspaceOpt` and `FormatOpt`.

- **`-o`:**
  - The output is written to a temporary file in the target folder, then moved into place with `os.replace`.
  - On Windows, a `PermissionError` is retried for up to 1 s, because indexers and antivirus scanners briefly lock new files. After that it becomes `output_not_writable`.
  - On success the runner writes the info line `output_written`.
- *Alternative:* writing the target in place. A failing Command, or one stopped halfway, would leave a truncated file behind.

### D14. Issues are read through 040's reader
Every Issue that `summary`, `issues`, `issues <rule-id>` and `page <url>` show comes from `040`'s Issues reader, which this change never bypasses:
- **Materialised** when `crawl.state` is `completed` or `stopped`: the `issues` view, whose `affected_count` is a COUNT over `affected_urls`, and `affected_urls` by its key prefix or by `affected_urls_url_id`.
- **Live** in every other state (`running`, `failed`, `interrupted`): every enabled Rule's `reproduce_sql`, run read-only over the stored rows. `affected_urls` is ignored, because after a resume it holds the previous pass's rows.
- `issues <rule-id>` adds the Rule's `reproduce_sql` to its `rule`, so an agent can rerun it with `sql` and read the Affected URLs as they are now.

### D15. Paging and index use
At about 500k URLs, what an index serves decides whether a call takes milliseconds or seconds. `docs/querying.md` lists this for each Command, and `080` documents it for agents.
- **`pages`:** the default order is `address`, served by `pages_address` (`030`, ruling Q6), so each page of a keyset walk reads only its rows. Any other `--sort`, and every `--where`, scans `pages` (there are no per-column indexes) and sorts the matches, once per page of results. Walking a large Crawl in another order is better done with a larger `--limit` or with `sql`. `contains` and, from v0.2, `~` call a Python function on every scanned row.
- **`issues`:** materialised, one scan of `affected_urls`' primary key grouped by Rule; live, every Rule's query.
- **`issues <rule-id>`:** materialised, the Rule's key prefix in `affected_urls`, joined to `pages` by key and sorted by `unique_inlinks`: the cost grows with the Issue's size, not the Crawl's. Live, the Rule's query on every call.
- **`page <url>`:** `urls_url` for the URL, then keys: `pages`, `response_headers`, the `redirect_url_id` hops, and `affected_urls_url_id` for its Issues when materialised. Live, every Rule's query for one URL, which `026`'s 500k run must keep under 1 s (`040` D16).
- **`summary`:** scans `urls` and `pages` (status classes, content types, Crawl Depth, Indexability) and sorts `response_time_ms` once (D8). No count over `urls` is stored, so this is seconds at 500k URLs, paid on every call.
  - *Hint:* the reads of `urls` (the totals, status classes, content types, Crawl Depth, and the count, min, max, mean and histogram of D8) can be one `GROUP BY` pass with conditional aggregates (`SUM(CASE …)`, `COUNT(*) FILTER (WHERE …)`) instead of one scan each. The breakdowns use different keys, so the pass may group by their combination and fold the small result in Python. The implementer measures it against the separate scans at 500k and keeps the faster. The percentile sort of D8 and the read of `pages` stay separate.
- **Suggestions:** `url_not_found` takes its candidates from `pages_address` around the given address (D18), never from a scan.

### D16. `summary` against Screaming Frog's Overview
Screaming Frog's Overview counts are the familiar reference, so the summary covers each of them or says why not:

| Overview | `summary` |
|---|---|
| Total URLs Encountered | `totals.encountered`: every `urls` row, queued and skipped ones included |
| Total URLs Crawled | `totals.crawled`: `fetch_state` `fetched` or `error` |
| Internal / External blocked by robots.txt | `status_classes.internal.blocked_by_robots_txt`, `status_classes.external.blocked_by_robots_txt` |
| Total Internal / External URLs | `totals.internal_urls`, `totals.external_urls` |
| Indexable / Non-Indexable | `indexability`, over Pages only: `030` records Indexability for Pages, while Screaming Frog also labels other Internal URLs |
| Content types with % of Total | `content_types`, per media type with `share_pct`, instead of Screaming Frog's coarse groups (HTML, JavaScript, CSS, Images, PDF, …) |

`totals.urls` keeps its meaning, the URLs with a recorded outcome, so `crawled` and `encountered` are added members and `summary_version` stays `1`. `status_classes` adds `record_failed`, which is the tool's failure and so belongs in neither `no_response` nor a status class (`040` makes the same exclusion).

### D17. A running Crawl: `summary` counts rows, `status` reads counters
`summary` counts the stored rows on every call, so a `running` Crawl shows what is committed so far, and the scans of D15 compete with the writer's WAL for as long as they run. `060`'s `status` is the cheap progress reading: its counts come from the progress counters that the heartbeat records, and it never counts over `urls` while a Crawl runs. This change does not read those counters: they are control data of a run, and they can lag the committed rows by a heartbeat. `docs/querying.md` points to `status` for polling.

### D18. Finding one URL
`page <url>` normalises its argument with `020`'s normaliser and looks it up through `urls_url`, so it accepts what the Crawl would have recorded. When there is no `pages` row, `details.suggestions` ranks with `difflib` the up to 50 addresses on each side of the given address in `pages_address` order. A difflib pass over 500k addresses would take seconds, while the neighbours in sort order share the longest prefix.

## Test seams

This change is tested at these seams from docs/testing.md:

- **Pure-logic modules (4):** the `--where` tokenizer, parser and compiler. Table-driven tests evaluate compiled expressions against an in-memory SQLite table that the test defines, including a boolean column. Hypothesis property tests cover two things: any printable string either parses or fails as `invalid_where`, and `not not (e)` matches the same rows as `e`.
- **Services and store API (2):** Query Service calls against real crawl stores in a temporary Workspace, with Segment definitions written to that Workspace's `spider.toml`.
- **CLI (1):** Typer `CliRunner` checks JSON output, exit codes, the diagnostics on stderr and `-o`. Real subprocess runs on Windows check console UTF-8, non-ASCII arguments, `page --html` output and CSV line endings on pipes.
  - The `csv` format, the CSV policy and `-o` are tested on 010's fixture app (`build_app(extra=…)` with the example list Command), before any query Command exists.
  - On Windows, a locked `-o` target is held by a real helper process that opens the file without sharing. It is not a double.
- **Store contract (6):** the `sql` refusals, limits and timeout. It is combined with the HTTP seam (**"3+6"**) where a scenario needs data that a real Crawl leaves behind: the cookie redaction seen through `page --headers`, and the summary contract on the fixture site.
- **HTTP fixture site (3):** see "3+6" above.

This change introduces no new seam and uses no boundary doubles. It adds one test aid, the **`crawl_store` factory**. It is a pytest fixture that builds a real crawl store from a compact description, and it writes only the tables and columns documented in `docs/schema.md`, through the public store API of `015-add-crawl-store` (seam 2). Its rows are therefore rows a real Crawl could leave behind (seam 6). It grows slice by slice: each task adds only the documented tables its scenario needs. It starts in the thin slice with `crawl`, `urls`, `pages`, `rules` and `affected_urls`. A `completed` Crawl it builds has its `affected_urls` rows and `health_*` fields, as `040`'s pass would leave them; a `running` one has neither, so the Issues reader computes them live from the stored rows. Memory is measured with `tracemalloc` at the Services seam.

## Risks / Trade-offs

- **Ordering depends on the TOML parser.** The TOML spec says key order is not significant, so a formatter that sorts keys would silently reorder Segments. → `tomllib` keeps document order. The docs warn about key-sorting formatters, and `summary.segments` and `details.accepted` of `unknown_segment` both show the evaluation order.
- **A broken Segment stops every Command,** because Segments are checked when settings load. → This is intended (G6). `settings_invalid` names the key `segments.<name>` and the `--where` error, so the fix is obvious.
- **Cost of query-time Segments.** At 500k Pages with regex-based Segments, a Python function runs per row per Segment, which takes seconds. → Membership is materialised once per `summary` call. `--segment` alone compiles to a single CASE, and simple comparisons stay native SQL.
- **Catastrophic regex backtracking in `--where`.** Python `re` has no timeout. → The pattern is the user's own, on their own machine. This is documented, and `sql --timeout` does not apply here.
- **A streamed export that fails midway** has already written some rows to stdout. → 010's rule for streams keeps the lines already written and ends with one error diagnostic and a non-zero exit, so consumers discard the partial output. With `-o`, D13 leaves the target untouched.
- **The byte-order mark surprises Unix tools such as `cut` and `awk`.** → `--no-bom` turns it off, and `docs/cli.md` shows it next to every CSV example.
- **Neutralisation changes text that starts with `-`,** such as `-webkit-` values, by adding `'`. → Accepted as the safe default for untrusted text. JSON and JSON Lines keep the raw value.
- **Some network filesystems and indexers hold new files.** → `-o` retries its rename for up to 1 s before reporting `output_not_writable`.
- **A summary or live Issues read during a large Crawl holds a read transaction for seconds,** and the WAL cannot be reset meanwhile. → `026`'s 500k run measures live Issues and their effect on checkpoints (`040` D16), and `docs/querying.md` points to `060`'s `status` for polling (D17).
- **Column-name assumptions in the scenarios.** → The scenarios follow 030's published names, and are renamed if 030 changes them. The behaviour does not change.

## Migration Plan

None. There are no schema changes and no stored state, so rollback means removing the Commands.

## Open Questions

- Should `sql` expose Segment membership, for example through a `segment_membership(address, segment)` temp view created before the authorizer is installed? This would be additive.
- Should `--where` allow column-to-column comparisons (`canonical_url != address`)? They are a syntax error today, so they could be added without breaking anything.
- Should `--segment` get a way to select the Pages in no Segment, and under what name? A reserved name could clash with a user's Segment. This would be additive.
- Should `summary` add exact `status_codes` counts next to `status_classes`? This would add a member, which the versioning rule allows.
