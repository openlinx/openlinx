> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each implementation task below is **one red → green slice** for one scenario, or for a trivial pair. Scenarios are named `Requirement › Scenario`, as in `specs/`.
1. Write the test at the named seam (docs/testing.md), with the literal expected values from the spec, and watch it fail for the right reason.
2. Write only enough code to pass it.
3. Run ruff, the strict type checker and pytest with coverage.
4. Make one commit whose message names the scenario.

**The thin slice** (ROADMAP, Build order) is group 1: `issues` and `issue <rule-id>` over `040`'s Issues reader, ending with the cross-OS end-to-end test. It needs no `--where`, no `pages` and no `summary`. Groups 2–8 widen the change to the rest of v0.1. Groups 9–13 are v0.2, and their tasks are marked (v0.2).

From group 1 on, the tests use the `crawl_store` factory (design.md, Test seams). It writes only tables and columns documented in `docs/schema.md`, through the store API of `015-add-crawl-store`. It grows in the slice that first needs a table. No boundary doubles are used.

Every group ends with a docs task and a review task.

## 1. `issues` and `issue <rule-id>` for the thin slice (slice; seams 2: Services, 1: CLI, 3+6)

- [x] 1.1 Drive `Issue list › Order` (Services). Start the `crawl_store` factory, a helper function in `tests/support/crawl_store.py`, with the documented `crawl`, `seeds`, `urls`, `pages`, `rules` and `affected_urls` tables, each written by its owner's store code (design, Test seams), and a `completed` Crawl carrying its `affected_urls` rows. The scenario's Issues A–D are Rules of a later tool, recorded as `RuleRow`s and passed over with the catalogue, as `040`'s reader tests do, since no registered Rule is a warning with high Priority or an issue with low Priority. Add the `issues` entry point of the Query Service in `spider.services.query`. It resolves the Crawl with `015`'s `resolve_crawl`, then reads in one `reading()`: `040`'s `issues_in`, joined to the Crawl's `rules` table for `description` (design D14). Verify: red → green; one commit.
- [x] 1.2 Drive `Issue list › Item fields` (Services). Verify: red → green; one commit.
- [x] 1.3 Drive `Issue list › Issues of a running Crawl are computed live` (Services): a `running` Crawl from the factory, with no `affected_urls` rows, read through the reader's live path (`040` task 3.14). Verify: red → green; one commit.
- [x] 1.4 Drive `Issue list › Filters combine` (CLI). Declare the `issues` Command with `@command_meta(output="list")`, returning a `Page` whose cursor fingerprint holds the resolved crawl id and the normalised filters (design D14). Its values are comma-separated, repeatable and case-insensitive. Verify: red → green; one commit.
- [x] 1.5 Drive `Issue list › Filter by category` (CLI). Verify: red → green; one commit.
- [x] 1.6 Drive `Issue list › Unknown Issue Type` (CLI). Verify: red → green; one commit.
- [x] 1.7 Drive `Issue detail › A Rule that did not fire` (Services): the detail entry point returns a `Page` with `header` `{"rule": ...}`, read from the Crawl's `rules` table, and its Affected URLs from `040`'s `affected_urls_in` on the same connection (design D14). The detail Command is `issue <rule-id>` (the user's decision of 2026-10-16, design D14), declared with task 1.13. Verify: red → green; one commit.
- [x] 1.8 Drive `Issue detail › Thresholds recorded for the Crawl` (Services). Verify: red → green; one commit.
- [x] 1.9 Drive `Issue detail › Guidance of the Rule` (Services). Verify: red → green; one commit.
- [x] 1.10 Drive `Issue detail › The reproducing query of the Rule` (Services): `reproduce_sql` in `rule`. Verify: red → green; one commit.
- [x] 1.11 Drive `Issue detail › Detail of an Affected URL` (Services). Verify: red → green; one commit.
- [x] 1.12 Drive the paging of Affected URLs (Services), a clause with no scenario of its own in `Issue detail` ("`--limit` and `--cursor` SHALL work as they do for `pages`"): items in `urls.url` order, paged by keyset in SQL through `affected_urls_in` joined to `urls`, the test listed in design Risks (design D4, D14). Verify: red → green; one commit.
- [ ] 1.13 Drive `Issue detail › Unknown rule id` (CLI), declaring the `issue <rule-id>` Command with its own `@command_meta` and its own fields, its cursor fingerprinted under `issue`, while `issues` takes no argument, so `spider issues <rule-id>` is a usage error and `spider commands` describes both truthfully: `040`'s `rule_not_found`, which its reader raises on both paths against the Crawl's `rules` table, with `details.suggestions` from that table (its task 4.11; design D14). Verify: red → green; one commit.
- [x] 1.14 Drive `Issue list › Issues of a fixture Crawl on every OS` (CLI and 3, real subprocesses on the Windows, macOS and Linux CI jobs, through `run_cli_process`, marked `slow`): add the `/e2e/` fixture pages, with `/e2e/gone` a `Status(404)` route; `spider crawl` then `spider issues`. `spider issue internal-4xx` follows, as a third subprocess (the rulings of 2026-10-16). This is the thin slice's end-to-end test. Verify: red → green on all three OSes; one commit.
- [ ] 1.15 Docs: in `docs/querying.md`, document `spider issues` and `spider issue <rule-id>`: the order, the filters, `affected_count`, `detail`, `reproduce_sql`, and that a `running`, `failed` or `interrupted` Crawl's Issues are computed live on every call. Until group 6, Affected URLs come in `url` order. Verify: every flag is documented.
- [x] 1.16 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green. Verify: suite green; one commit.
- [x] 1.17 Close the approval of group 1 (the rulings of 2026-10-15): non-scenario tests prove the order of Issue Types and Priorities, the `url` order of Affected URLs apart from their insertion order, the cursor's binding to the Crawl and the filters of the list and to the Crawl of the detail, the whole `rule` header and a later Rule's `description` read from the Crawl's `rules` table (`later_rule` gets texts of its own), and `keyset_page` with `--limit 0` and with an exactly full last page; `issue_list` checks `--fields` and the cursor before it reads the Issues; the empty-value message quotes the value; design D14 says that a read is one snapshot in WAL mode only; `keyset_after` and `keyset_page` take a tuple of keys, checked by length and exact type, so group 6's (`unique_inlinks`, `url`) keeps one cursor shape; and `spider.store.query` decodes a `detail` with `040`'s reader's own function. Verify: suite green; one commit.

## 2. The basic `--where` language (seam 4: Pure-logic)

- [ ] 2.1 Drive `Where filter language › Comparison`: a tokenizer, a recursive-descent parser and the AST in `spider.query`, which loads no `sqlalchemy`, and the compiler to Core in `spider.store.query` (design Context, D1), for `column compare literal`, evaluated on an in-memory SQLite table defined by the test. Verify: red → green; one commit.
- [ ] 2.2 Drive `Where filter language › and requires both`. Verify: red → green; one commit.
- [ ] 2.3 Drive `Where filter language › Column names are case-insensitive`. Verify: red → green; one commit.
- [ ] 2.4 Drive `Where filter language › contains ignores case in any script`: the `spider_contains` casefold function. Verify: red → green; one commit.
- [ ] 2.5 Drive `Where filter language › is null and is not null`. Verify: red → green; one commit.
- [ ] 2.6 Drive the pair `Where filter language › Doubled quotes inside a string` and `› Double-quoted string`. Verify: red → green; one commit.
- [ ] 2.7 Drive `Where filter language › Boolean literal`. Verify: red → green; one commit.
- [ ] 2.8 Drive `Null values in filters › A comparison excludes null values`: wrap predicates in `IS NOT NULL AND`. Verify: red → green; one commit.
- [ ] 2.9 Drive `Null values in filters › Not-equal excludes null values`. Verify: red → green; one commit.
- [ ] 2.10 Drive `Filter syntax errors › Any input either parses or fails cleanly` with a hypothesis text strategy. Verify: the property passes; one commit.
- [ ] 2.11 Docs: write the where-language reference in `docs/querying.md`: the v0.1 grammar (comparisons, `contains`, `is [not] null` and `and`), the null rule, quoting in PowerShell and cmd (double quotes outside, single quotes inside), and the error codes. Verify: every v0.1 operator has an example.
- [ ] 2.12 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 3. Query foundation and `pages` (seams 2: Services, 1: CLI)

- [ ] 3.1 Drive `Query Commands read the selected Crawl without changing it › A specific Crawl is selected` (Services). Add the Query Service `pages` entry point, using 015's `--crawl` resolution and returning `total`. Verify: red → green; one commit.
- [ ] 3.2 Drive `Page listing › Default fields` (Services): the six default fields in 010's envelope. Verify: red → green; one commit.
- [ ] 3.3 Drive the pair `Page listing › Selected fields` and `› All fields` (Services): the available fields are the `pages` columns in `spider schema` order. Verify: red → green; one commit.
- [ ] 3.4 Drive `Unknown names in --where, --sort and --fields › Unknown field in --fields` (CLI): the `spider pages` Typer command, raising 010's `unknown_field`. Verify: red → green; one commit.
- [ ] 3.5 Drive `Page listing › Filtered listing` (CLI): wire `--where` into `pages`. Verify: red → green; one commit.
- [ ] 3.6 Drive `Query error codes › Error shape` (CLI). Verify: red → green; one commit.
- [ ] 3.7 Drive `Unknown names in --where, --sort and --fields › Unknown column in --where` (CLI): `unknown_column` with `details.suggestions` from `difflib`. Verify: red → green; one commit.
- [ ] 3.8 Drive the pair `Filter values fit the column type › String compared with a number column` and `› Number compared with a text column` (CLI). Verify: red → green; one commit.
- [ ] 3.9 Drive `Filter values fit the column type › Invalid regular expression` (CLI). Verify: red → green; one commit.
- [ ] 3.10 Drive `Filter syntax errors › Position of a syntax error` (CLI). Verify: red → green; one commit.
- [ ] 3.11 Drive `Filter syntax errors › SQL cannot be smuggled in` (CLI). Verify: red → green; one commit.
- [ ] 3.12 Drive `Filter syntax errors › A smuggling attempt leaves the store unchanged` (CLI, SQL dump before and after). Verify: red → green; one commit.
- [ ] 3.13 Drive `Sorting › Default order` (Services). Verify: red → green; one commit.
- [ ] 3.14 Drive `Sorting › Several keys, one descending` (Services). Verify: red → green; one commit.
- [ ] 3.15 Drive the pair `Sorting › Nulls sort last when descending` and `› Nulls sort last when ascending` (Services): `(col IS NULL), col`. Verify: red → green; one commit.
- [ ] 3.16 Drive `Sorting › Repeated flag` (CLI). Verify: red → green; one commit.
- [ ] 3.17 Drive `Sorting › Malformed sort` (CLI). Verify: red → green; one commit.
- [ ] 3.18 Drive `Unknown names in --where, --sort and --fields › Unknown column in --sort` (CLI). Verify: red → green; one commit.
- [ ] 3.19 Drive `Page listing › Total counts every match` (Services): the keyset payload inside 010's cursor. Verify: red → green; one commit.
- [ ] 3.20 Drive `Sorting › Paging is stable while the Crawl writes` (Services, with rows added through the store API between pages). Verify: red → green; one commit.
- [ ] 3.21 Drive `Cursors are bound to the query › A cursor is reused with another filter` (CLI): pass the Crawl, `--where` and `--sort` to 010's cursor binding. Verify: red → green; one commit.
- [ ] 3.22 Drive `Page listing › Non-ASCII titles on the Windows console` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 3.23 Drive `Where filter language › Non-ASCII literal passed on the Windows command line` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 3.24 Docs: in `docs/querying.md`, document `spider pages`: the default fields, `--fields all`, the `--sort` syntax (with `--sort=-col` for shells that read a leading `-` as a flag), and paging, with what is served by `pages_address` and what scans (design D15). Verify: every flag of `pages` is documented.
- [ ] 3.25 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 4. `page <url>` (seams 2: Services, 1: CLI, 3+6)

- [ ] 4.1 Drive `Single URL detail › No redirect` (Services): the `page` entry point, finding the URL through `020`'s normaliser and `urls_url` (design D18), with `url`, `columns`, an empty `redirect_chain` and `html_stored`. Verify: red → green; one commit.
- [ ] 4.2 Drive `Single URL detail › Redirect Chain` (Services): follow the hops that 022 records, using the documented `urls` redirect columns in the factory. Verify: red → green; one commit.
- [ ] 4.3 Drive `Single URL detail › Issues of the URL` (Services). The Issues of the URL come through `040`'s Issues reader (design D14). Verify: red → green; one commit.
- [ ] 4.4 Drive `Single URL detail › Link counts in a Section Crawl` (Services). Verify: red → green; one commit.
- [ ] 4.5 Drive `Single URL detail › Fragment and host case are ignored` (Services). Verify: red → green; one commit.
- [ ] 4.6 Drive the pair `Single URL detail › Unknown URL` and `Query error codes › Not-found class` (CLI): `url_not_found` with `details.suggestions` ranked from the `pages_address` neighbours of the argument's display form, `030`'s `display_address` (design D18). Verify: red → green; one commit.
- [ ] 4.7 Drive `Response headers of a URL › Repeated headers are kept` (Services). Extend the factory with the documented `response_headers` table. Verify: red → green; one commit.
- [ ] 4.8 Drive `Response headers of a URL › No headers member by default` (Services). Verify: red → green; one commit.
- [ ] 4.9 Drive `Response headers of a URL › Headers not recorded` (CLI). Verify: red → green; one commit.
- [ ] 4.10 Drive `Response headers of a URL › Cookie values are not shown` (3+6: crawl the fixture page `/cookie`, then run `page --headers`). Verify: red → green; one commit.
- [ ] 4.11 Docs: in `docs/querying.md`, document `spider page`: its members, `--headers` with redacted cookies, and `headers_not_stored`. Verify: every member of the `page` output is documented.
- [ ] 4.12 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 5. `summary` (seams 2: Services, 1: CLI, 3+6)

- [ ] 5.1 Drive `Summary Crawl metadata › Whole-site Crawl` (Services): the msgspec `SummaryModel` and its `crawl` member. Verify: red → green; one commit.
- [ ] 5.2 Drive `Query Commands read the selected Crawl without changing it › The latest Crawl is used by default` (Services). Verify: red → green; one commit.
- [ ] 5.3 Drive `Summary Crawl metadata › Section Crawl flag` (Services). Verify: red → green; one commit.
- [ ] 5.4 Drive `Summary Crawl metadata › List Crawl with many Seeds` (Services). Verify: red → green; one commit.
- [ ] 5.5 Drive `Summary Crawl metadata › Crawl stopped with Ctrl+C` (Services): `state`, `stop_reason` and `completed_at`. Verify: red → green; one commit.
- [ ] 5.6 Drive `Query Commands read the selected Crawl without changing it › A running Crawl can be queried` (Services). Verify: red → green; one commit.
- [ ] 5.7 Drive `Summary URL counts › Totals` (Services): `encountered`, `crawled` and the counts of design D16. Verify: red → green; one commit.
- [ ] 5.8 Drive `Summary URL counts › Status classes` (Services), from the documented `fetch_state`, `skip_reason`, `fetch_error` and `status_code` columns, with `record_failed` apart from `no_response`. Verify: red → green; one commit.
- [ ] 5.9 Drive `Summary URL counts › Indexability` (Services). Verify: red → green; one commit.
- [ ] 5.10 Drive `Summary URL counts › Content types` (Services): media-type normalisation, `share_pct`, with `null` last. Verify: red → green; one commit.
- [ ] 5.11 Drive `Summary URL counts › Crawl Depth distribution` (Services). Verify: red → green; one commit.
- [ ] 5.12 Drive `Summary Crawl metadata › Crawl Depth of a Section Crawl is labelled partial` (Services). Verify: red → green; one commit.
- [ ] 5.13 Drive `Summary response-time statistics › Statistics` (Services): nearest-rank percentiles from one sorted read (design D8). Verify: red → green; one commit.
- [ ] 5.14 Drive `Summary response-time statistics › Histogram` (Services). Verify: red → green; one commit.
- [ ] 5.15 Drive `Summary response-time statistics › No responses` (Services). Verify: red → green; one commit.
- [ ] 5.16 Drive `Summary Health Score and Issues › Health Score components` (Services), a `running` Crawl, calling 040's Health Score function over the live Affected URLs (design D7). Verify: red → green; one commit.
- [ ] 5.17 Drive `Summary Health Score and Issues › A finished Crawl's Health Score is the stored one` (Services): read the derived `health_*` fields of a `completed` Crawl (design D7). Verify: red → green; one commit.
- [ ] 5.18 Drive `Summary Health Score and Issues › No Internal Pages` (Services). Verify: red → green; one commit.
- [ ] 5.19 Drive `Summary Health Score and Issues › Issue counts by Issue Type and Priority` (Services). Verify: red → green; one commit.
- [ ] 5.20 Drive `Summary Health Score and Issues › Top Issues` (Services). Verify: red → green; one commit.
- [ ] 5.21 Drive `Summary Health Score and Issues › Top out of range` (CLI). Verify: red → green; one commit.
- [ ] 5.22 Drive the pair `Summary JSON contract › Top-level members` and `› Summary version` (CLI). Verify: red → green; one commit.
- [ ] 5.23 Drive `Summary for people › Table output` (CLI). Verify: red → green; one commit.
- [ ] 5.24 Drive `Summary for people › CSV is refused` (CLI). Verify: red → green; one commit.
- [ ] 5.25 Drive `Summary JSON contract › Contract on the fixture site` (3+6 and CLI): add the reference pages to the fixture site and hand-write the expected summary JSON, with no generated snapshot. Verify: red → green on all three OSes; one commit.
- [ ] 5.26 Docs: write `docs/contracts/summary.md`: every member, its type and meaning, the `summary_version` rule, a full example, the mapping to Screaming Frog's Overview (design D16), the note that `status` is the cheap progress reading of a running Crawl (design D17), and the note that the Report (070) uses this model. Verify: the example decodes into `SummaryModel` in a doc test.
- [ ] 5.27 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 6. `issue <rule-id>` widening (seams 2: Services)

- [ ] 6.1 Drive `Issue detail › Most-linked Affected URLs first` (Services), once `030`'s inlink columns exist. Verify: red → green; one commit.
- [ ] 6.2 Drive `Issue detail › Page columns for Affected URLs` (Services), reusing `--where` and `--sort` from groups 1 and 3. Verify: red → green; one commit.
- [ ] 6.3 Docs: in `docs/querying.md`, document the default order by Unique Inlinks, and the page columns of Affected URLs. Verify: every flag of `issue <rule-id>` is documented.
- [ ] 6.4 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 7. `sql` (seams 6: Store contract, 1: CLI)

- [ ] 7.1 Drive `Read-only SQL › A SELECT runs` (Store contract): the result shape on 015's read-only connection. Verify: red → green; one commit.
- [ ] 7.2 Drive `SQL results › Duplicate column names` (Store contract). Verify: red → green; one commit.
- [ ] 7.3 Drive `SQL results › BLOB values` (Store contract). Verify: red → green; one commit.
- [ ] 7.4 Drive `Read-only SQL › Writes are refused` (Store contract): the statement check. Verify: red → green; one commit.
- [ ] 7.5 Drive `Read-only SQL › A refused write changes nothing` (Store contract). Verify: red → green; one commit.
- [ ] 7.6 Drive the pair `Read-only SQL › Two statements are refused` and `› PRAGMA is refused` (Store contract). Verify: red → green; one commit.
- [ ] 7.7 Drive `Read-only SQL › A WITH that writes is refused` (Store contract): the authorizer allowlist. Verify: red → green; one commit.
- [ ] 7.8 Drive `Read-only SQL › ATTACH is refused` (Store contract). Verify: red → green; one commit.
- [ ] 7.9 Drive `Read-only SQL › Loading an extension is refused` (Store contract). Verify: red → green; one commit.
- [ ] 7.10 Drive the pair `SQL results › Default row limit` and `› Custom row limit` (CLI): `fetchmany(limit + 1)` and `truncated`. Verify: red → green; one commit.
- [ ] 7.11 Drive `SQL errors, timeout and query files › Unknown column` (CLI): `details.suggestions` from schema metadata. Verify: red → green; one commit.
- [ ] 7.12 Drive `SQL errors, timeout and query files › Timeout` (CLI): the progress-handler timeout. Verify: red → green; one commit.
- [ ] 7.13 Drive `SQL errors, timeout and query files › Query given twice` (CLI). Verify: red → green; one commit.
- [ ] 7.14 Drive `SQL errors, timeout and query files › Query file with a byte-order mark on Windows` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 7.15 Docs: in `docs/querying.md`, document `spider sql`: what is refused and why, the result shape, `--limit`, `--timeout`, `--file`, and a pointer to `spider schema`. Verify: every refused statement class is listed.
- [ ] 7.16 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 8. Cross-cutting checks (seam 1: CLI)

- [ ] 8.1 Drive `Query Commands read the selected Crawl without changing it › Queries leave the store unchanged` (CLI): a SQL dump before and after running every query Command. Verify: red → green; one commit.
- [ ] 8.2 Drive `Query Commands are self-described › The flags of pages are listed` (CLI). Verify: red → green; one commit.
- [ ] 8.3 Drive `Query Commands are self-described › Output kinds` (CLI). Verify: red → green; one commit.
- [ ] 8.4 Drive `Query Commands are self-described › The diagnostic codes of sql are listed` (CLI). Verify: red → green; one commit.
- [ ] 8.5 Docs: add the query Commands to the README command overview, and link `docs/querying.md`, `docs/segments.md` and `docs/contracts/summary.md`. Verify: links resolve.
- [ ] 8.6 Review: run the code-review skill on group 8's commits and on the v0.1 part of the change against its specs, then refactor with the whole suite green. Verify: suite green on Windows, macOS and Linux; one commit.

## 9. (v0.2) The rest of the `--where` language (seam 4: Pure-logic)

- [ ] 9.1 (v0.2) Drive `Where filter language › and binds tighter than or`. Verify: red → green; one commit.
- [ ] 9.2 (v0.2) Drive `Where filter language › Parentheses override precedence`. Verify: red → green; one commit.
- [ ] 9.3 (v0.2) Drive `Where filter language › not`. Verify: red → green; one commit.
- [ ] 9.4 (v0.2) Drive `Where filter language › Keywords are case-insensitive`. Verify: red → green; one commit.
- [ ] 9.5 (v0.2) Drive `Where filter language › Regular expression`: the `spider_regexp` SQLite function with a pattern cache. Verify: red → green; one commit.
- [ ] 9.6 (v0.2) Drive the pair `Where filter language › Regular expressions are case-sensitive by default` and `› Case-insensitive regular expression`. Verify: red → green; one commit.
- [ ] 9.7 (v0.2) Drive `Where filter language › Negated regular expression`. Verify: red → green; one commit.
- [ ] 9.8 (v0.2) Drive `Where filter language › Backslashes reach the regular expression unchanged`. Verify: red → green; one commit.
- [ ] 9.9 (v0.2) Drive `Where filter language › Regular expression on a number column`: match on `CAST(col AS TEXT)`. Verify: red → green; one commit.
- [ ] 9.10 (v0.2) Drive `Where filter language › not contains`. Verify: red → green; one commit.
- [ ] 9.11 (v0.2) Drive `Where filter language › in and not in`. Verify: red → green; one commit.
- [ ] 9.12 (v0.2) Drive `Null values in filters › not includes null values`. Verify: red → green; one commit.
- [ ] 9.13 (v0.2) Drive `Null values in filters › Double negation changes nothing`: a hypothesis generator of grammar-valid expressions over rows with nulls. Verify: the property passes with the default hypothesis profile; one commit.
- [ ] 9.14 (v0.2) Drive `Filter syntax errors › Nesting limit`: a depth cap of 64. Verify: red → green; one commit.
- [ ] 9.15 (v0.2) Docs: add `or`, `not`, parentheses, `~`, `!~`, `in` and `not contains`, the regex dialect and the nesting limit to the where-language reference in `docs/querying.md`. Verify: every operator in the spec grammar has an example.
- [ ] 9.16 (v0.2) Review: run the code-review skill on group 9's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 10. (v0.2) The `csv` format, the CSV policy and `-o` (seam 1: CLI, 010's fixture app)

- [ ] 10.1 (v0.2) Drive `CSV policy › Byte-order mark and CRLF` (CLI): accept `csv` in `FormatOpt` for list Commands, and add the CSV writer of design D12. Verify: red → green; one commit.
- [ ] 10.2 (v0.2) Drive the pair `CSV policy › Without the byte-order mark` and `› The byte-order mark flag needs CSV` (CLI): `NoBomOpt`. Verify: red → green; one commit.
- [ ] 10.3 (v0.2) Drive `CSV policy › Formula-like text is neutralised` (CLI). Verify: red → green; one commit.
- [ ] 10.4 (v0.2) Drive `CSV policy › Numbers are unchanged` (CLI). Verify: red → green; one commit.
- [ ] 10.5 (v0.2) Drive `CSV policy › Nested value and null` (CLI). Verify: red → green; one commit.
- [ ] 10.6 (v0.2) Drive `CSV policy › A document is one CSV row` (CLI): `csv` for document Commands, and for `spider init`. Verify: red → green; one commit.
- [ ] 10.7 (v0.2) Drive `CSV format › Rows as CSV` (CLI): `csv` for rows Commands, written and flushed row by row. Verify: red → green; one commit.
- [ ] 10.8 (v0.2) Drive `CSV format › More items notice in CSV` (CLI): the info line `more_items` for `csv` too. Verify: red → green; one commit.
- [ ] 10.9 (v0.2) Pin `CSV format › spider commands refuses CSV` (CLI). The test passes on its first run, because `spider commands` keeps `json` and `table`, and it is kept to pin the contract. Verify: green; one commit.
- [ ] 10.10 (v0.2) Drive `Writing output to a file with -o › Output goes to the file` (CLI): `OutputOpt`, written to a temporary file in the target folder and then moved into place with `os.replace`. Verify: red → green; one commit.
- [ ] 10.11 (v0.2) Drive `Writing output to a file with -o › Nothing on stdout with -o` (CLI). Verify: red → green; one commit.
- [ ] 10.12 (v0.2) Drive `Writing output to a file with -o › The written file is reported` (CLI): the info line `output_written`. Verify: red → green; one commit.
- [ ] 10.13 (v0.2) Drive `Writing output to a file with -o › Parent folders are created` (CLI). Verify: red → green; one commit.
- [ ] 10.14 (v0.2) Drive the pair `Writing output to a file with -o › A failing Command keeps the old file` and `› A failing Command creates no file` (CLI). Verify: red → green; one commit.
- [ ] 10.15 (v0.2) Drive `Writing output to a file with -o › Target held open on Windows` (CLI, real subprocess, Windows-only): a Windows-only helper process holds the file open without sharing. Green: `output_not_writable` with exit code 7, after up to 1 s of retries. Verify: red → green on the Windows CI job; one commit.
- [ ] 10.16 (v0.2) Drive the pair `Global flags --no-bom and -o › -o after the Command name` and `› -o before the Command name` (CLI): add `--no-bom` and `--output` to 010's `argv` check for global flags. Verify: red → green; one commit.
- [ ] 10.17 (v0.2) Drive `Global flags --no-bom and -o › Global output flags of init` (CLI): `global` in the option metadata of `NoBomOpt` and `OutputOpt`. Verify: red → green; one commit.
- [ ] 10.18 (v0.2) Drive `Global flags --no-bom and -o › Output-file flags have no settings key` (CLI): `"setting":null` for `--no-bom` and `--output`, and no `spider.toml` key for them in 010's settings registry. Verify: red → green; one commit.
- [ ] 10.19 (v0.2) Drive the pair `CSV format › Formats of a document Command` and `› Formats of a list Command` (CLI). Verify: red → green; one commit.
- [ ] 10.20 (v0.2) Drive the pair `Diagnostic codes of output files › Error code of output files` and `› Info line of output files` (CLI): register `output_not_writable` (exit code 7) and `output_written`. Verify: red → green; one commit.
- [ ] 10.21 (v0.2) Update the `init` entry of 010's hand-written contract JSON in `tests/contract/commands/`: `"formats":["json","table","csv"]`, and the options `--no-bom` and `--output` with `"global":true` and `"setting":null`. Edit it by hand, never by regenerating it. Verify: 010's `Self-description with spider commands › Same description on every OS` is green on Windows, macOS and Linux; one commit.
- [ ] 10.22 (v0.2) Docs: in `docs/cli.md`, add `csv` to the formats, the CSV policy with a `--no-bom` example, and `-o` with a PowerShell example. Verify: every rule of the requirements `CSV format`, `CSV policy` and `Writing output to a file with -o` is documented.
- [ ] 10.23 (v0.2) Review: run the code-review skill on group 10's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 11. (v0.2) `page <url> --html` (seams 2: Services, 1: CLI)

- [ ] 11.1 (v0.2) Drive `Raw HTML of a Page › Stored HTML` (Services). Extend the factory with the documented `page_sources` table. Verify: red → green; one commit.
- [ ] 11.2 (v0.2) Drive `Raw HTML of a Page › HTML decoded from windows-1251` (Services). Verify: red → green; one commit.
- [ ] 11.3 (v0.2) Drive `Raw HTML of a Page › No html member by default` (Services). Verify: red → green; one commit.
- [ ] 11.4 (v0.2) Drive `Raw HTML of a Page › HTML and headers together` (Services). Verify: red → green; one commit.
- [ ] 11.5 (v0.2) Drive `Raw HTML of a Page › HTML not stored` (CLI): `html_not_stored` with the hint that names `crawl --store-html`. Verify: red → green; one commit.
- [ ] 11.6 (v0.2) Drive `Raw HTML of a Page › HTML on the Windows console` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 11.7 (v0.2) Docs: in `docs/querying.md`, document `--html` with `encoding`, and `html_not_stored`. Verify: every member `--html` adds is documented.
- [ ] 11.8 (v0.2) Review: run the code-review skill on group 11's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 12. (v0.2) Segments (seams 2: Services, 1: CLI)

- [ ] 12.1 (v0.2) Drive `Segment definitions in spider.toml › Membership follows the expressions` (Services): read `[segments]` in document order, compile it to one CASE expression, and offer the `segment` field. Verify: red → green; one commit.
- [ ] 12.2 (v0.2) Drive `First match wins › Overlapping Segments` (Services, through `page`). Verify: red → green; one commit.
- [ ] 12.3 (v0.2) Drive `First match wins › Reordering changes membership` (Services). Verify: red → green; one commit.
- [ ] 12.4 (v0.2) Drive `First match wins › A Page in no Segment` (Services). Verify: red → green; one commit.
- [ ] 12.5 (v0.2) Drive `Segment definitions are checked when settings load › Unknown column in a Segment expression` (CLI): register the `[segments]` validator in 010's settings check, compiling against the static `pages` table definition. Verify: red → green; one commit.
- [ ] 12.6 (v0.2) Drive `Segment definitions are checked when settings load › The problem is named` (CLI). Verify: red → green; one commit.
- [ ] 12.7 (v0.2) Drive `Segment definitions are checked when settings load › Invalid Segment name` (CLI). Verify: red → green; one commit.
- [ ] 12.8 (v0.2) Drive `Segment definitions are checked when settings load › Commands that do not use Segments are stopped too` (CLI). Verify: red → green; one commit.
- [ ] 12.9 (v0.2) Drive `The --segment flag › Pages of one Segment` (Services). Verify: red → green; one commit.
- [ ] 12.10 (v0.2) Drive `The --segment flag › A Page won by an earlier Segment is not in a later one` (Services). Verify: red → green; one commit.
- [ ] 12.11 (v0.2) Drive `The --segment flag › --segment combines with --where` (Services). Verify: red → green; one commit.
- [ ] 12.12 (v0.2) Drive the pair `The --segment flag › Unknown Segment name` and `Query error codes › Accepted values in details` (CLI). Verify: red → green; one commit.
- [ ] 12.13 (v0.2) Drive `The --segment flag › Commands list the --segment flag` (CLI). Verify: red → green; one commit.
- [ ] 12.14 (v0.2) Drive `The --segment flag › --segment without any Segments defined` (CLI). Verify: red → green; one commit.
- [ ] 12.15 (v0.2) Drive `The segment field › All fields include the Segment` (Services). Verify: red → green; one commit.
- [ ] 12.16 (v0.2) Drive `The segment field › Sorting by Segment` (Services). Verify: red → green; one commit.
- [ ] 12.17 (v0.2) Drive `The segment field › segment in --where` (CLI). Verify: red → green; one commit.
- [ ] 12.18 (v0.2) Drive `Cursors are bound to the query › A cursor is reused with another Segment` (CLI). Verify: red → green; one commit.
- [ ] 12.19 (v0.2) Drive `Segments are applied at query time › Editing a definition changes the next result` (CLI, with `spider.toml` edited between runs). Verify: red → green; one commit.
- [ ] 12.20 (v0.2) Drive `Segments are applied at query time › Segment changes do not touch the store` (CLI). Verify: red → green; one commit.
- [ ] 12.21 (v0.2) Drive `Segments are applied at query time › Older Crawls use the current definitions` (CLI). Verify: red → green; one commit.
- [ ] 12.22 (v0.2) Drive `Per-Segment breakdown in summary › Entries add up to all Pages` (Services): TEMP-table membership, built once per call. Verify: red → green; one commit.
- [ ] 12.23 (v0.2) Drive `Segment definitions in spider.toml › Segments in file order` (Services). Verify: red → green; one commit.
- [ ] 12.24 (v0.2) Drive `Per-Segment breakdown in summary › Entry members` (Services). Verify: red → green; one commit.
- [ ] 12.25 (v0.2) Drive `Per-Segment breakdown in summary › Summary without any Segments defined` (Services). Verify: red → green; one commit.
- [ ] 12.26 (v0.2) Drive `Per-Segment breakdown in summary › Issues per Segment` (Services). Verify: red → green; one commit.
- [ ] 12.27 (v0.2) Drive `Health Score of a Segment › Empty Segment` (Services). Verify: red → green; one commit.
- [ ] 12.28 (v0.2) Drive `Health Score of a Segment › Health Score of one Segment` (Services). Verify: red → green; one commit.
- [ ] 12.29 (v0.2) Drive `Summary of one Segment › Totals of one Segment` (Services). Verify: red → green; one commit.
- [ ] 12.30 (v0.2) Drive the pair `Summary of one Segment › Segment members of a one-Segment summary` and `› Whole-Crawl summary` (Services). Verify: red → green; one commit.
- [ ] 12.31 (v0.2) Drive `Issues within a Segment › Counts within a Segment` (Services). Verify: red → green; one commit.
- [ ] 12.32 (v0.2) Drive `Issues within a Segment › Issues without Affected URLs in the Segment are omitted` (Services). Verify: red → green; one commit.
- [ ] 12.33 (v0.2) Drive `Issues within a Segment › Resources belong to no Segment` (Services). Verify: red → green; one commit.
- [ ] 12.34 (v0.2) Drive `Issues within a Segment › Affected URLs of one Issue within a Segment` (Services). Verify: red → green; one commit.
- [ ] 12.35 (v0.2) Docs: write `docs/segments.md`: the `[segments]` table, the naming rule, the check at load time, first match wins, query-time evaluation, the warning about key-sorting TOML formatters, and examples for blog, shop and locale folders. Verify: every requirement of the `segments` spec is covered.
- [ ] 12.36 (v0.2) Review: run the code-review skill on group 12's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 13. (v0.2) `export` (seams 1: CLI, 2: Services)

- [ ] 13.1 (v0.2) Drive `Export formats › JSONL keeps nulls` (CLI): the `pages` view streamed through 010's NDJSON serialiser. Verify: red → green; one commit.
- [ ] 13.2 (v0.2) Drive `Export formats › CSV follows the CSV policy` (CLI), using the CSV writer of group 2 row by row. Verify: red → green; one commit.
- [ ] 13.3 (v0.2) Drive `Export formats › Unsupported format` (CLI). Verify: red → green; one commit.
- [ ] 13.4 (v0.2) Drive `Export formats › Export is a rows Command` (CLI). Verify: red → green; one commit.
- [ ] 13.5 (v0.2) Drive `Export streams its rows › Rows go to the -o file` (CLI), relying on the `-o` of group 2. Verify: red → green; one commit.
- [ ] 13.6 (v0.2) Drive `Export streams its rows › Bounded memory` (Services, `tracemalloc` peaks with 200,000 and 1,000 Pages built by the factory). Verify: red → green; one commit.
- [ ] 13.7 (v0.2) Drive `Export views › Issues view` (CLI). Verify: red → green; one commit.
- [ ] 13.8 (v0.2) Drive `Export views › Affected URLs of one Rule` (CLI). Verify: red → green; one commit.
- [ ] 13.9 (v0.2) Drive `Export views › Link rows name their URLs` (CLI). Extend the factory with the documented `links` table. Verify: red → green; one commit.
- [ ] 13.10 (v0.2) Drive `Export views › Links of a Segment` (CLI). Verify: red → green; one commit.
- [ ] 13.11 (v0.2) Drive `Export views › Resource columns` (CLI): the `resources` query over `urls` and `links`. Verify: red → green; one commit.
- [ ] 13.12 (v0.2) Drive `Export views › A Page is not a Resource` (CLI). Verify: red → green; one commit.
- [ ] 13.13 (v0.2) Drive `Export views › Resources of a Segment` (CLI). Verify: red → green; one commit.
- [ ] 13.14 (v0.2) Drive `Export views › Unknown view` (CLI). Verify: red → green; one commit.
- [ ] 13.15 (v0.2) Drive `Export streams its rows › No doubled carriage returns on the Windows console` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 13.16 (v0.2) Drive `Export streams its rows › Export leaves the store unchanged` (CLI): a SQL dump before and after. Verify: red → green; one commit.
- [ ] 13.17 (v0.2) Docs: in `docs/querying.md`, document `spider export`: the views and their columns, the Resource definition, the formats with a pointer to the CSV policy in `docs/cli.md`, and opening a CSV in Excel on Windows. Verify: every view and flag is documented.
- [ ] 13.18 (v0.2) Review: run the code-review skill on group 13's commits and on the change as a whole against its three specs, then refactor with the whole suite green. Verify: suite green on Windows, macOS and Linux; one commit.
