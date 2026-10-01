Each implementation task below is **one red → green slice** for one scenario, or for a trivial pair. Scenarios are named `Requirement › Scenario`, as in `specs/`.
1. Write the test at the named seam (docs/testing.md), with the literal expected values from the spec, and watch it fail for the right reason.
2. Write only enough code to pass it.
3. Run ruff, the strict type checker and pytest with coverage.
4. Make one commit whose message names the scenario.

From group 3 on, the tests use the `crawl_store` factory (design.md, Test seams). It writes only tables and columns documented in `docs/schema.md`, through the store API of `015-add-crawl-store`. It grows in the slice that first needs a table. No boundary doubles are used.

Every group ends with a docs task and a review task.

## 1. The `--where` language (seam 4: Pure-logic)

- [ ] 1.1 Drive `Where filter language › Comparison`: a tokenizer, a recursive-descent parser and a Core compiler for `column compare literal`, evaluated on an in-memory SQLite table defined by the test. Verify: red → green; one commit.
- [ ] 1.2 Drive `Where filter language › and binds tighter than or`. Verify: red → green; one commit.
- [ ] 1.3 Drive `Where filter language › Parentheses override precedence`. Verify: red → green; one commit.
- [ ] 1.4 Drive `Where filter language › not`. Verify: red → green; one commit.
- [ ] 1.5 Drive the pair `Where filter language › Keywords are case-insensitive` and `› Column names are case-insensitive`. Verify: red → green; one commit.
- [ ] 1.6 Drive `Where filter language › Regular expression`: the `spider_regexp` SQLite function with a pattern cache. Verify: red → green; one commit.
- [ ] 1.7 Drive the pair `Where filter language › Regular expressions are case-sensitive by default` and `› Case-insensitive regular expression`. Verify: red → green; one commit.
- [ ] 1.8 Drive `Where filter language › Negated regular expression`. Verify: red → green; one commit.
- [ ] 1.9 Drive `Where filter language › Backslashes reach the regular expression unchanged`. Verify: red → green; one commit.
- [ ] 1.10 Drive `Where filter language › Regular expression on a number column`: match on `CAST(col AS TEXT)`. Verify: red → green; one commit.
- [ ] 1.11 Drive `Where filter language › contains ignores case in any script`: the `spider_contains` casefold function. Verify: red → green; one commit.
- [ ] 1.12 Drive `Where filter language › not contains`. Verify: red → green; one commit.
- [ ] 1.13 Drive `Where filter language › in and not in`. Verify: red → green; one commit.
- [ ] 1.14 Drive `Where filter language › is null and is not null`. Verify: red → green; one commit.
- [ ] 1.15 Drive the pair `Where filter language › Doubled quotes inside a string` and `› Double-quoted string`. Verify: red → green; one commit.
- [ ] 1.16 Drive `Where filter language › Boolean literal`. Verify: red → green; one commit.
- [ ] 1.17 Drive `Null values in filters › A comparison excludes null values`: wrap predicates in `IS NOT NULL AND`. Verify: red → green; one commit.
- [ ] 1.18 Drive `Null values in filters › not includes null values`. Verify: red → green; one commit.
- [ ] 1.19 Drive `Null values in filters › Not-equal excludes null values`. Verify: red → green; one commit.
- [ ] 1.20 Drive `Null values in filters › Double negation changes nothing`: a hypothesis generator of grammar-valid expressions over rows with nulls. Verify: the property passes with the default hypothesis profile; one commit.
- [ ] 1.21 Drive `Filter syntax errors › Any input either parses or fails cleanly` with a hypothesis text strategy. Verify: the property passes; one commit.
- [ ] 1.22 Drive `Filter syntax errors › Nesting limit`: a depth cap of 64. Verify: red → green; one commit.
- [ ] 1.23 Docs: write the where-language reference in `docs/querying.md`: the grammar, operators, the null rule, the regex dialect, quoting in PowerShell and cmd (double quotes outside, single quotes inside), and the error codes. Verify: every operator in the spec grammar has an example.
- [ ] 1.24 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green. Verify: findings resolved or recorded; one commit.

## 2. The `csv` format, the CSV policy and `-o` (seam 1: CLI, 010's fixture app)

These slices run on 010's fixture app: `build_app(extra=…)` with the example list Command, its rows Command and its lists with the CSV edge values. They need no Crawl, so they come before the query Commands, and `export` (group 9) reuses their writer. The writer and the `-o` target live in 010's output layer `spider.output` (design D12, D13). A slice that changes what `spider commands` prints also updates, in the same commit, the 010 tests that pin the old value, so the suite stays green.

- [ ] 2.1 Drive `CSV policy › Byte-order mark and CRLF` (CLI): accept `csv` in `FormatOpt` for list Commands, and add the CSV writer of design D12. Verify: red → green; one commit.
- [ ] 2.2 Drive the pair `CSV policy › Without the byte-order mark` and `› The byte-order mark flag needs CSV` (CLI): `NoBomOpt`. Verify: red → green; one commit.
- [ ] 2.3 Drive `CSV policy › Formula-like text is neutralised` (CLI). Verify: red → green; one commit.
- [ ] 2.4 Drive `CSV policy › Numbers are unchanged` (CLI). Verify: red → green; one commit.
- [ ] 2.5 Drive `CSV policy › Nested value and null` (CLI). Verify: red → green; one commit.
- [ ] 2.6 Drive `CSV policy › A document is one CSV row` (CLI): `csv` for document Commands, and for `spider init`. Verify: red → green; one commit.
- [ ] 2.7 Drive `CSV format › Rows as CSV` (CLI): `csv` for rows Commands, written and flushed row by row. Verify: red → green; one commit.
- [ ] 2.8 Drive `CSV format › More items notice` (CLI): the info line `more_items` for `csv` too. Verify: red → green; one commit.
- [ ] 2.9 Pin `CSV format › spider commands refuses CSV` (CLI). The test passes on its first run, because `spider commands` keeps `json` and `table`, and it is kept to pin the contract. Verify: green; one commit.
- [ ] 2.10 Drive `Writing output to a file with -o › Output goes to the file` (CLI): `OutputOpt`, written to a temporary file in the target folder and then moved into place with `os.replace`. Verify: red → green; one commit.
- [ ] 2.11 Drive `Writing output to a file with -o › Nothing on stdout with -o` (CLI). Verify: red → green; one commit.
- [ ] 2.12 Drive `Writing output to a file with -o › The written file is reported` (CLI): the info line `output_written`. Verify: red → green; one commit.
- [ ] 2.13 Drive `Writing output to a file with -o › Parent folders are created` (CLI). Verify: red → green; one commit.
- [ ] 2.14 Drive the pair `Writing output to a file with -o › A failing Command keeps the old file` and `› A failing Command creates no file` (CLI). Verify: red → green; one commit.
- [ ] 2.15 Drive `Writing output to a file with -o › Target held open on Windows` (CLI, real subprocess, Windows-only): a Windows-only helper process holds the file open without sharing. Green: `output_not_writable` with exit code 7, after up to 1 s of retries. Verify: red → green on the Windows CI job; one commit.
- [ ] 2.16 Drive the pair `Global flags --no-bom and -o › After the Command name` and `› Before the Command name` (CLI): add `--no-bom` and `--output` to 010's `argv` check for global flags. Verify: red → green; one commit.
- [ ] 2.17 Drive `Global flags --no-bom and -o › Global flags of init` (CLI): `global` in the option metadata of `NoBomOpt` and `OutputOpt`. Verify: red → green; one commit.
- [ ] 2.18 Drive `Global flags --no-bom and -o › Output flags have no settings key` (CLI): `"setting":null` for `--no-bom` and `--output`, and no `spider.toml` key for them in 010's settings registry. Verify: red → green; one commit.
- [ ] 2.19 Drive the pair `CSV format › Formats of a document Command` and `› Formats of a list Command` (CLI). Verify: red → green; one commit.
- [ ] 2.20 Drive the pair `Diagnostic codes of output files › Error code of output files` and `› Info line of output files` (CLI): register `output_not_writable` (exit code 7) and `output_written`. Verify: red → green; one commit.
- [ ] 2.21 Update the `init` entry of 010's hand-written contract JSON in `tests/contract/commands/`: `"formats":["json","table","csv"]`, and the options `--no-bom` and `--output` with `"global":true` and `"setting":null`. Edit it by hand, never by regenerating it. Verify: 010's `Self-description with spider commands › Same description on every OS` is green on Windows, macOS and Linux; one commit.
- [ ] 2.22 Docs: in `docs/cli.md`, add `csv` to the formats, the CSV policy with a `--no-bom` example, and `-o` with a PowerShell example. Verify: every rule of the requirements `CSV format`, `CSV policy` and `Writing output to a file with -o` is documented.
- [ ] 2.23 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green. Verify: findings resolved or recorded; one commit.

## 3. Query foundation and `pages` (seams 2: Services, 1: CLI)

- [ ] 3.1 Drive `Query Commands read the selected Crawl without changing it › A specific Crawl is selected` (Services). Start the `crawl_store` factory with the documented `crawl`, `seeds`, `urls` and `pages` tables, and add the Query Service `pages` entry point, using 015's `--crawl` resolution and returning `total`. Verify: red → green; one commit.
- [ ] 3.2 Drive `Page listing › Default fields` (Services): the six default fields in 010's envelope. Verify: red → green; one commit.
- [ ] 3.3 Drive the pair `Page listing › Selected fields` and `› All fields` (Services): the available fields are the `pages` columns in `spider schema` order, then `segment`. Verify: red → green; one commit.
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
- [ ] 3.24 Docs: in `docs/querying.md`, document `spider pages`: the default fields, `--fields all`, the `--sort` syntax (with `--sort=-col` for shells that read a leading `-` as a flag), and paging. Verify: every flag of `pages` is documented.
- [ ] 3.25 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 4. `page <url>` (seams 2: Services, 1: CLI, 3+6)

- [ ] 4.1 Drive `Single URL detail › No redirect` (Services): the `page` entry point with `url`, `columns`, an empty `redirect_chain` and `html_stored`. Verify: red → green; one commit.
- [ ] 4.2 Drive `Single URL detail › Redirect Chain` (Services): follow the hops that 022 records, using the documented `urls` redirect columns in the factory. Verify: red → green; one commit.
- [ ] 4.3 Drive `Single URL detail › Issues of the URL` (Services). Extend the factory with the documented `rules`, `issues` and `affected_urls` tables. Verify: red → green; one commit.
- [ ] 4.4 Drive `Single URL detail › Link counts in a Section Crawl` (Services). Verify: red → green; one commit.
- [ ] 4.5 Drive `Single URL detail › Fragment and host case are ignored` (Services). Verify: red → green; one commit.
- [ ] 4.6 Drive the pair `Single URL detail › Unknown URL` and `Query error codes › Not-found class` (CLI): `url_not_found` with `details.suggestions`. Verify: red → green; one commit.
- [ ] 4.7 Drive `Raw HTML of a Page › Stored HTML` (Services). Extend the factory with the documented `page_sources` table. Verify: red → green; one commit.
- [ ] 4.8 Drive `Raw HTML of a Page › HTML decoded from windows-1251` (Services). Verify: red → green; one commit.
- [ ] 4.9 Drive `Raw HTML of a Page › No html member by default` (Services). Verify: red → green; one commit.
- [ ] 4.10 Drive `Raw HTML of a Page › HTML not stored` (CLI): `html_not_stored` with the `--store-html` hint. Verify: red → green; one commit.
- [ ] 4.11 Drive `Raw HTML of a Page › HTML on the Windows console` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 4.12 Drive `Response headers of a URL › Repeated headers are kept` (Services). Extend the factory with the documented `response_headers` table. Verify: red → green; one commit.
- [ ] 4.13 Drive the pair `Response headers of a URL › No headers member by default` and `Raw HTML of a Page › HTML and headers together` (Services). Verify: red → green; one commit.
- [ ] 4.14 Drive `Response headers of a URL › Headers not recorded` (CLI). Verify: red → green; one commit.
- [ ] 4.15 Drive `Response headers of a URL › Cookie values are not shown` (3+6: crawl the fixture page `/cookie`, then run `page --headers`). Verify: red → green; one commit.
- [ ] 4.16 Docs: in `docs/querying.md`, document `spider page`: its members, `--html` with `encoding`, `--headers` with redacted cookies, and the not-stored errors. Verify: every member of the `page` output is documented.
- [ ] 4.17 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 5. Segments (seams 2: Services, 1: CLI)

- [ ] 5.1 Drive `Segment definitions in spider.toml › Membership follows the expressions` (Services): read `[segments]` in document order, compile it to one CASE expression, and offer the `segment` field. Verify: red → green; one commit.
- [ ] 5.2 Drive `First match wins › Overlapping Segments` (Services, through `page`). Verify: red → green; one commit.
- [ ] 5.3 Drive `First match wins › Reordering changes membership` (Services). Verify: red → green; one commit.
- [ ] 5.4 Drive `First match wins › A Page in no Segment` (Services). Verify: red → green; one commit.
- [ ] 5.5 Drive `Segment definitions are checked when settings load › Unknown column in a Segment expression` (CLI): register the `[segments]` validator in 010's settings check, compiling against the static `pages` table definition. Verify: red → green; one commit.
- [ ] 5.6 Drive `Segment definitions are checked when settings load › The problem is named` (CLI). Verify: red → green; one commit.
- [ ] 5.7 Drive `Segment definitions are checked when settings load › Invalid Segment name` (CLI). Verify: red → green; one commit.
- [ ] 5.8 Drive `Segment definitions are checked when settings load › Commands that do not use Segments are stopped too` (CLI). Verify: red → green; one commit.
- [ ] 5.9 Drive `The --segment flag › Pages of one Segment` (Services). Verify: red → green; one commit.
- [ ] 5.10 Drive `The --segment flag › A Page won by an earlier Segment is not in a later one` (Services). Verify: red → green; one commit.
- [ ] 5.11 Drive `The --segment flag › --segment combines with --where` (Services). Verify: red → green; one commit.
- [ ] 5.12 Drive the pair `The --segment flag › Unknown Segment name` and `Query error codes › Accepted values in details` (CLI). Verify: red → green; one commit.
- [ ] 5.13 Drive `The --segment flag › No Segments defined` (CLI). Verify: red → green; one commit.
- [ ] 5.14 Drive `The segment field › Sorting by Segment` (Services). Verify: red → green; one commit.
- [ ] 5.15 Drive `The segment field › segment in --where` (CLI). Verify: red → green; one commit.
- [ ] 5.16 Drive `Cursors are bound to the query › A cursor is reused with another Segment` (CLI). Verify: red → green; one commit.
- [ ] 5.17 Drive `Segments are applied at query time › Editing a definition changes the next result` (CLI, with `spider.toml` edited between runs). Verify: red → green; one commit.
- [ ] 5.18 Drive `Segments are applied at query time › Segment changes do not touch the store` (CLI). Verify: red → green; one commit.
- [ ] 5.19 Drive `Segments are applied at query time › Older Crawls use the current definitions` (CLI). Verify: red → green; one commit.
- [ ] 5.20 Docs: write `docs/segments.md`: the `[segments]` table, the naming rule, the check at load time, first match wins, query-time evaluation, the warning about key-sorting TOML formatters, and examples for blog, shop and locale folders. Verify: every requirement of the `segments` spec is covered.
- [ ] 5.21 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 6. `summary` (seams 2: Services, 1: CLI, 3+6)

- [ ] 6.1 Drive `Summary Crawl metadata › Whole-site Crawl` (Services): the msgspec `SummaryModel` and its `crawl` member. Verify: red → green; one commit.
- [ ] 6.2 Drive `Query Commands read the selected Crawl without changing it › The latest Crawl is used by default` (Services). Verify: red → green; one commit.
- [ ] 6.3 Drive `Summary Crawl metadata › Section Crawl flag` (Services). Verify: red → green; one commit.
- [ ] 6.4 Drive `Summary Crawl metadata › List Crawl with many Seeds` (Services). Verify: red → green; one commit.
- [ ] 6.5 Drive `Summary Crawl metadata › Crawl stopped with Ctrl+C` (Services): `state`, `stop_reason` and `completed_at`. Verify: red → green; one commit.
- [ ] 6.6 Drive `Query Commands read the selected Crawl without changing it › A running Crawl can be queried` (Services). Verify: red → green; one commit.
- [ ] 6.7 Drive `Summary URL counts › Totals` (Services). Verify: red → green; one commit.
- [ ] 6.8 Drive `Summary URL counts › Status classes` (Services), from the documented `fetch_state`, `skip_reason` and `status_code` columns. Verify: red → green; one commit.
- [ ] 6.9 Drive `Summary URL counts › Indexability` (Services). Verify: red → green; one commit.
- [ ] 6.10 Drive `Summary URL counts › Content types` (Services): media-type normalisation, with `null` last. Verify: red → green; one commit.
- [ ] 6.11 Drive `Summary URL counts › Crawl Depth distribution` (Services). Verify: red → green; one commit.
- [ ] 6.12 Drive `Summary Crawl metadata › Crawl Depth of a Section Crawl is labelled partial` (Services). Verify: red → green; one commit.
- [ ] 6.13 Drive `Summary response-time statistics › Statistics` (Services): nearest-rank percentiles. Verify: red → green; one commit.
- [ ] 6.14 Drive `Summary response-time statistics › Histogram` (Services). Verify: red → green; one commit.
- [ ] 6.15 Drive `Summary response-time statistics › No responses` (Services). Verify: red → green; one commit.
- [ ] 6.16 Drive `Summary Health Score and Issues › Health Score components` (Services), calling 040's Health Score function. Verify: red → green; one commit.
- [ ] 6.17 Drive `Summary Health Score and Issues › No Internal Pages` (Services). Verify: red → green; one commit.
- [ ] 6.18 Drive `Summary Health Score and Issues › Issue counts by Issue Type and Priority` (Services). Verify: red → green; one commit.
- [ ] 6.19 Drive `Summary Health Score and Issues › Top Issues` (Services). Verify: red → green; one commit.
- [ ] 6.20 Drive `Summary Health Score and Issues › Top out of range` (CLI). Verify: red → green; one commit.
- [ ] 6.21 Drive the pair `Summary JSON contract › Top-level members` and `› Summary version` (CLI). Verify: red → green; one commit.
- [ ] 6.22 Drive `Per-Segment breakdown in summary › Entries add up to all Pages` (Services): TEMP-table membership, built once per call. Verify: red → green; one commit.
- [ ] 6.23 Drive `Segment definitions in spider.toml › Segments in file order` (Services). Verify: red → green; one commit.
- [ ] 6.24 Drive `Per-Segment breakdown in summary › Entry members` (Services). Verify: red → green; one commit.
- [ ] 6.25 Drive `Per-Segment breakdown in summary › No Segments defined` (Services). Verify: red → green; one commit.
- [ ] 6.26 Drive `Per-Segment breakdown in summary › Issues per Segment` (Services). Verify: red → green; one commit.
- [ ] 6.27 Drive `Health Score of a Segment › Empty Segment` (Services). Verify: red → green; one commit.
- [ ] 6.28 Drive `Health Score of a Segment › Health Score of one Segment` (Services). Verify: red → green; one commit.
- [ ] 6.29 Drive `Summary of one Segment › Totals of one Segment` (Services). Verify: red → green; one commit.
- [ ] 6.30 Drive the pair `Summary of one Segment › Segment members of a one-Segment summary` and `› Whole-Crawl summary` (Services). Verify: red → green; one commit.
- [ ] 6.31 Drive `Summary for people › Table output` (CLI). Verify: red → green; one commit.
- [ ] 6.32 Drive `Summary for people › CSV is refused` (CLI). Verify: red → green; one commit.
- [ ] 6.33 Drive `Summary JSON contract › Contract on the fixture site` (3+6 and CLI): add the reference pages to the fixture site and hand-write the expected summary JSON, with no generated snapshot. Verify: red → green on all three OSes; one commit.
- [ ] 6.34 Docs: write `docs/contracts/summary.md`: every member, its type and meaning, the `summary_version` rule, a full example, and the note that the Report (070) uses this model. Verify: the example decodes into `SummaryModel` in a doc test.
- [ ] 6.35 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 7. `issues` and `issues <rule-id>` (seams 2: Services, 1: CLI)

- [ ] 7.1 Drive `Issue list › Order` (Services): read `issues` joined with the Crawl's `rules` table. Verify: red → green; one commit.
- [ ] 7.2 Drive `Issue list › Item fields` (Services). Verify: red → green; one commit.
- [ ] 7.3 Drive `Issue list › Filters combine` (CLI): comma-separated, repeatable, case-insensitive values. Verify: red → green; one commit.
- [ ] 7.4 Drive `Issue list › Filter by category` (CLI). Verify: red → green; one commit.
- [ ] 7.5 Drive `Issue list › Unknown Issue Type` (CLI). Verify: red → green; one commit.
- [ ] 7.6 Drive `Issue detail › Most-linked Affected URLs first` (Services). Verify: red → green; one commit.
- [ ] 7.7 Drive `Issue detail › A Rule that did not fire` (Services). Verify: red → green; one commit.
- [ ] 7.8 Drive `Issue detail › Thresholds recorded for the Crawl` (Services). Verify: red → green; one commit.
- [ ] 7.9 Drive `Issue detail › Guidance of the Rule` (Services). Verify: red → green; one commit.
- [ ] 7.10 Drive `Issue detail › Detail of an Affected URL` (Services). Verify: red → green; one commit.
- [ ] 7.11 Drive `Issue detail › Page columns for Affected URLs` (Services), reusing `--where` and `--sort` from groups 1 and 3. Verify: red → green; one commit.
- [ ] 7.12 Drive `Issue detail › Unknown rule id` (CLI): 040's `rule_not_found` with `details.suggestions`. Verify: red → green; one commit.
- [ ] 7.13 Drive `Issues within a Segment › Counts within a Segment` (Services). Verify: red → green; one commit.
- [ ] 7.14 Drive `Issues within a Segment › Issues without Affected URLs in the Segment are omitted` (Services). Verify: red → green; one commit.
- [ ] 7.15 Drive `Issues within a Segment › Resources belong to no Segment` (Services). Verify: red → green; one commit.
- [ ] 7.16 Drive `Issues within a Segment › Affected URLs of one Issue within a Segment` (Services). Verify: red → green; one commit.
- [ ] 7.17 Docs: in `docs/querying.md`, document `spider issues` and `spider issues <rule-id>`: the order, the filters, `affected_count`, `detail`, and the default order by Unique Inlinks. Verify: every flag is documented.
- [ ] 7.18 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 8. `sql` (seams 6: Store contract, 1: CLI)

- [ ] 8.1 Drive `Read-only SQL › A SELECT runs` (Store contract): the result shape on 015's read-only connection. Verify: red → green; one commit.
- [ ] 8.2 Drive `SQL results › Duplicate column names` (Store contract). Verify: red → green; one commit.
- [ ] 8.3 Drive `SQL results › BLOB values` (Store contract). Verify: red → green; one commit.
- [ ] 8.4 Drive `Read-only SQL › Writes are refused` (Store contract): the statement check. Verify: red → green; one commit.
- [ ] 8.5 Drive `Read-only SQL › A refused write changes nothing` (Store contract). Verify: red → green; one commit.
- [ ] 8.6 Drive the pair `Read-only SQL › Two statements are refused` and `› PRAGMA is refused` (Store contract). Verify: red → green; one commit.
- [ ] 8.7 Drive `Read-only SQL › A WITH that writes is refused` (Store contract): the authorizer allowlist. Verify: red → green; one commit.
- [ ] 8.8 Drive `Read-only SQL › ATTACH is refused` (Store contract). Verify: red → green; one commit.
- [ ] 8.9 Drive `Read-only SQL › Loading an extension is refused` (Store contract). Verify: red → green; one commit.
- [ ] 8.10 Drive the pair `SQL results › Default row limit` and `› Custom row limit` (CLI): `fetchmany(limit + 1)` and `truncated`. Verify: red → green; one commit.
- [ ] 8.11 Drive `SQL errors, timeout and query files › Unknown column` (CLI): `details.suggestions` from schema metadata. Verify: red → green; one commit.
- [ ] 8.12 Drive `SQL errors, timeout and query files › Timeout` (CLI): the progress-handler timeout. Verify: red → green; one commit.
- [ ] 8.13 Drive `SQL errors, timeout and query files › Query given twice` (CLI). Verify: red → green; one commit.
- [ ] 8.14 Drive `SQL errors, timeout and query files › Query file with a byte-order mark on Windows` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 8.15 Docs: in `docs/querying.md`, document `spider sql`: what is refused and why, the result shape, `--limit`, `--timeout`, `--file`, and a pointer to `spider schema`. Verify: every refused statement class is listed.
- [ ] 8.16 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 9. `export` (seams 1: CLI, 2: Services)

- [ ] 9.1 Drive `Export formats › JSONL keeps nulls` (CLI): the `pages` view streamed through 010's NDJSON serialiser. Verify: red → green; one commit.
- [ ] 9.2 Drive `Export formats › CSV follows the CSV policy` (CLI), using the CSV writer of group 2 row by row. Verify: red → green; one commit.
- [ ] 9.3 Drive `Export formats › Unsupported format` (CLI). Verify: red → green; one commit.
- [ ] 9.4 Drive `Export streams its rows › Rows go to the -o file` (CLI), relying on the `-o` of group 2. Verify: red → green; one commit.
- [ ] 9.5 Drive `Export streams its rows › Bounded memory` (Services, `tracemalloc` peaks with 200,000 and 1,000 Pages built by the factory). Verify: red → green; one commit.
- [ ] 9.6 Drive `Export views › Issues view` (CLI). Verify: red → green; one commit.
- [ ] 9.7 Drive `Export views › Affected URLs of one Rule` (CLI). Verify: red → green; one commit.
- [ ] 9.8 Drive `Export views › Link rows name their URLs` (CLI). Extend the factory with the documented `links` table. Verify: red → green; one commit.
- [ ] 9.9 Drive `Export views › Links of a Segment` (CLI). Verify: red → green; one commit.
- [ ] 9.10 Drive `Export views › Resource columns` (CLI): the `resources` query over `urls` and `links`. Verify: red → green; one commit.
- [ ] 9.11 Drive `Export views › A Page is not a Resource` (CLI). Verify: red → green; one commit.
- [ ] 9.12 Drive `Export views › Resources of a Segment` (CLI). Verify: red → green; one commit.
- [ ] 9.13 Drive `Export views › Unknown view` (CLI). Verify: red → green; one commit.
- [ ] 9.14 Drive `Export streams its rows › No doubled carriage returns on the Windows console` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 9.15 Docs: in `docs/querying.md`, document `spider export`: the views and their columns, the Resource definition, the formats with a pointer to the CSV policy in `docs/cli.md`, and opening a CSV in Excel on Windows. Verify: every view and flag is documented.
- [ ] 9.16 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 10. Cross-cutting checks (seam 1: CLI)

- [ ] 10.1 Drive `Query Commands read the selected Crawl without changing it › Queries leave the store unchanged` (CLI): a SQL dump before and after running every query Command. Verify: red → green; one commit.
- [ ] 10.2 Drive `Query Commands are self-described › The flags of pages are listed` (CLI). Verify: red → green; one commit.
- [ ] 10.3 Drive `Query Commands are self-described › Output kinds` (CLI). Verify: red → green; one commit.
- [ ] 10.4 Drive `Query Commands are self-described › The diagnostic codes of sql are listed` (CLI). Verify: red → green; one commit.
- [ ] 10.5 Docs: add the query Commands to the README command overview, and link `docs/querying.md`, `docs/segments.md` and `docs/contracts/summary.md`. Verify: links resolve.
- [ ] 10.6 Review: run the code-review skill on group 10's commits and on the change as a whole against its three specs, then refactor with the whole suite green. Verify: suite green on Windows, macOS and Linux; one commit.
