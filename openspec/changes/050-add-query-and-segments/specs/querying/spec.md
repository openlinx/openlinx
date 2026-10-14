## Purpose

Lets agents and people read a Crawl through stable, token-efficient Commands: an overview (`summary`), filtered Page lists written in the `--where` language, one URL in detail, the Issues, read-only SQL and bulk export. Their JSON shapes are contracts that the Report, the Skill and the MCP server build on.

## ADDED Requirements

### Requirement: Query Commands read the selected Crawl without changing it

The `summary`, `pages`, `page`, `issues`, `sql` and, from v0.2, `export` Commands SHALL read the Crawl that the `--crawl` option selects. That option, `latest|<id>|<path>` with the default `latest`, is defined by `015-add-crawl-store`. The Commands SHALL NOT modify the crawl store, they SHALL work while the selected Crawl is still running, and each invocation SHALL read one consistent snapshot of the store.

#### Scenario: The latest Crawl is used by default
- **WHEN** the Workspace holds Crawl A, started first and `completed`, and Crawl B, started second
- **AND** `spider summary` runs without `--crawl`
- **THEN** the output's `crawl.id` is the id of Crawl B

#### Scenario: A specific Crawl is selected
- **WHEN** the Workspace holds Crawl A with 3 Pages and Crawl B with 5 Pages
- **AND** `spider pages --crawl <id of Crawl A>` runs
- **THEN** the output's `total` is `3`

#### Scenario: A running Crawl can be queried
- **WHEN** the latest Crawl is in the Crawl State `running` and has stored 4 Pages so far
- **AND** `spider summary` runs
- **THEN** the output has `"state": "running"` in `crawl` and `"pages": 4` in `totals`

#### Scenario: Queries leave the store unchanged
- **WHEN** `spider summary`, `spider pages`, `spider page https://example.com/`, `spider issues` and `spider sql "SELECT 1"` each run once against a `completed` Crawl
- **THEN** a SQL dump of the crawl store taken afterwards is identical to one taken before they ran

### Requirement: Query Commands are self-described

`spider commands --format json`, the self-description defined by `010-add-workspace-and-cli-contract`, SHALL describe the `summary`, `pages`, `page`, `issues`, `sql` and `export` Commands. The description SHALL include each Command's output kind, every flag this capability defines for it, and every diagnostic code it can emit. The output kinds SHALL be:
- `document` for `summary`, `page` and `sql`
- `list` for `pages` and `issues`
- `rows` for `export` (v0.2)

#### Scenario: The flags of pages are listed
- **WHEN** `spider commands --format json` runs
- **THEN** the entry for `pages` lists the flags `--where`, `--fields`, `--sort`, `--limit` and `--cursor`

#### Scenario: Output kinds
- **WHEN** `spider commands --format json` runs
- **THEN** the entries for `summary`, `pages` and `sql` have the output kinds `document`, `list` and `document`

#### Scenario: The diagnostic codes of sql are listed
- **WHEN** `spider commands --format json` runs
- **THEN** the diagnostic codes listed for `sql` include `sql_not_allowed`, `sql_error` and `sql_timeout`

### Requirement: Summary Crawl metadata

`spider summary` SHALL return one JSON object. Its `crawl` member SHALL describe the Crawl with these fields, taken from the crawl metadata of `015-add-crawl-store` and `020-add-crawl-core`:

| Field | Value |
|---|---|
| `id` | the Crawl id |
| `seeds` | the first 10 Seeds, in the order recorded |
| `seed_count` | the number of Seeds |
| `crawl_mode` | `spider`, `list` or `sitemap` |
| `state` | the Crawl State: `running`, `stopped`, `completed`, `failed` or `interrupted` |
| `stop_reason` | why a `stopped` or `failed` Crawl ended, one of the six values of `020-add-crawl-core` (for example `interrupt` or `site_unreachable`); otherwise `null` |
| `started_at`, `completed_at` | ISO 8601 UTC timestamps; `completed_at` is the time the Crawl State became `completed`, and `null` in every other state |
| `section_crawl` | `true` when the Crawl is a Section Crawl |
| `link_metrics` | `"partial"` for a Section Crawl, otherwise `"complete"` |
| `tool_version`, `schema_version` | the version of the tool that ran the Crawl, and the crawl store schema version |

#### Scenario: Whole-site Crawl
- **WHEN** a `completed` Spider-mode Crawl with the single Seed `https://example.com/` is summarised
- **THEN** `crawl` contains `"crawl_mode": "spider"`, `"seeds": ["https://example.com/"]`, `"seed_count": 1`, `"state": "completed"`, `"section_crawl": false` and `"link_metrics": "complete"`

#### Scenario: Section Crawl flag
- **WHEN** a `completed` Section Crawl is summarised
- **THEN** `crawl` contains `"section_crawl": true` and `"link_metrics": "partial"`

#### Scenario: Crawl Depth of a Section Crawl is labelled partial
- **WHEN** a `completed` Section Crawl is summarised
- **THEN** `crawl_depth.partial` is `true`

#### Scenario: List Crawl with many Seeds
- **WHEN** a List-mode Crawl started from the 25 URLs `https://example.com/p1` to `https://example.com/p25`, in that order, is summarised
- **THEN** `crawl.seed_count` is `25` and `crawl.seeds` is the 10 URLs `https://example.com/p1` to `https://example.com/p10` in that order

#### Scenario: Crawl stopped with Ctrl+C
- **WHEN** a Crawl that was stopped with Ctrl+C is summarised
- **THEN** `crawl` contains `"state": "stopped"`, `"stop_reason": "interrupt"` and `"completed_at": null`

### Requirement: Summary URL counts

The summary SHALL include these members:

- `totals`: `encountered` (every URL the Crawl recorded, queued and skipped ones included), `crawled` (URLs that were requested: `fetch_state` `fetched` or `error`), `urls` (URLs with a recorded outcome: the crawled ones and those not requested because robots.txt disallows them), `internal_urls` and `external_urls` (the Internal and External URLs among `urls`), `pages` and `resources`. Resources are defined as for the `resources` export view.
- `status_classes`: two objects, `internal` and `external`. Each always has exactly the keys `2xx`, `3xx`, `4xx`, `5xx`, `other` (any other status code), `no_response` (the request failed without an HTTP response), `record_failed` (the Crawl got a response but could not record it, `020-add-crawl-core`'s `fetch_error` `record_failed`, which is the tool's failure, never the site's) and `blocked_by_robots_txt` (not requested because robots.txt disallows it). Each URL is counted once, by its own status code; a URL fetched under `--ignore-robots` is counted by its status code.
- `indexability`: `indexable`, `non_indexable`, and `by_status`, a list of `{status, count}` for the Indexability Statuses of Non-Indexable URLs, ordered by count descending and then by status. It covers the Pages, because `030-add-page-data` records Indexability only for Pages.
- `content_types`: a list of `{content_type, count, share_pct}` for Internal URLs that returned a response. The media type is lowercased and its parameters are removed, and it is `null` when there was no Content-Type header. `share_pct` is 100 × `count` ÷ the number of those URLs, rounded to 2 decimals. The list is ordered by count descending and then by content type, with `null` last.
- `crawl_depth`: `{partial, max, distribution}`, where `distribution` has one `{depth, count}` entry for every depth from 0 to `max`, zeros included. It covers the Internal URLs whose Crawl Depth is recorded. When there are none, `max` is `null` and `distribution` is empty.

#### Scenario: Totals
- **WHEN** a Crawl requested 6 Internal URLs (4 Pages and 2 Resources) and 3 External URLs that are not Resources, did not request 1 Internal URL that robots.txt disallows, and still has 2 discovered URLs queued
- **THEN** `totals` is `{"encountered": 12, "crawled": 9, "urls": 10, "internal_urls": 7, "external_urls": 3, "pages": 4, "resources": 2}`

#### Scenario: Status classes
- **WHEN** a Crawl recorded Internal URLs with the status codes 200, 200, 301, 404, 503 and 999, one Internal URL whose request timed out, one Internal URL whose response could not be recorded (`record_failed`), one Internal URL blocked by robots.txt, and one External URL with status code 404
- **THEN** `status_classes` is `{"internal": {"2xx": 2, "3xx": 1, "4xx": 1, "5xx": 1, "other": 1, "no_response": 1, "record_failed": 1, "blocked_by_robots_txt": 1}, "external": {"2xx": 0, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0, "no_response": 0, "record_failed": 0, "blocked_by_robots_txt": 0}}`

#### Scenario: Indexability
- **WHEN** a Crawl recorded 3 Indexable Pages, 1 Non-Indexable Page with Indexability Status `noindex` and 1 with Indexability Status `canonicalised`
- **THEN** `indexability` is `{"indexable": 3, "non_indexable": 2, "by_status": [{"status": "canonicalised", "count": 1}, {"status": "noindex", "count": 1}]}`

#### Scenario: Content types
- **WHEN** four Internal URLs responded with the Content-Type headers `text/html; charset=utf-8` and `text/HTML`, `image/png`, and no Content-Type header
- **THEN** `content_types` is `[{"content_type": "text/html", "count": 2, "share_pct": 50.00}, {"content_type": "image/png", "count": 1, "share_pct": 25.00}, {"content_type": null, "count": 1, "share_pct": 25.00}]`

#### Scenario: Crawl Depth distribution
- **WHEN** a Crawl recorded Internal URLs with the Crawl Depths 0, 1, 1 and 3
- **THEN** `crawl_depth` is `{"partial": false, "max": 3, "distribution": [{"depth": 0, "count": 1}, {"depth": 1, "count": 2}, {"depth": 2, "count": 0}, {"depth": 3, "count": 1}]}`

### Requirement: Summary response-time statistics

The summary's `response_time_ms` member SHALL cover the Internal URLs that returned a response. Its fields are `count`, `min`, `mean` (rounded to one decimal place), `p50`, `p90`, `p95`, `p99` and `max`, all in milliseconds. The percentiles use the nearest-rank method: the value at rank ceil(P/100 × count) in ascending order. Every field except `count` is `null` when `count` is 0. A `histogram` member SHALL always have seven buckets, `{from_ms, to_ms, count}`, with the bounds 0–100, 100–250, 250–500, 500–1000, 1000–2000, 2000–5000 and 5000 upwards. The lower bound is inclusive, the upper bound exclusive, and the last bucket's `to_ms` is `null`.

#### Scenario: Statistics
- **WHEN** Internal URLs responded in 50, 100, 150, 200, 300, 450, 800, 1200, 2500 and 6000 ms
- **THEN** `response_time_ms` contains `"count": 10`, `"min": 50`, `"mean": 1175.0`, `"p50": 300`, `"p90": 2500`, `"p95": 6000`, `"p99": 6000` and `"max": 6000`

#### Scenario: Histogram
- **WHEN** Internal URLs responded in 50, 100, 150, 200, 300, 450, 800, 1200, 2500 and 6000 ms
- **THEN** the `count` values of `response_time_ms.histogram`, in bucket order, are `[1, 3, 2, 1, 1, 1, 1]`

#### Scenario: No responses
- **WHEN** no Internal URL of the Crawl returned a response
- **THEN** `response_time_ms` has `"count": 0`, `null` for `min`, `mean`, `p50`, `p90`, `p95`, `p99` and `max`, and seven histogram buckets whose counts are all `0`

### Requirement: Summary Health Score and Issues

The summary's `health_score` member SHALL be `{score, internal_pages, affected_pages}`:
- `internal_pages` is the number of Internal Pages.
- `affected_pages` is the number of those that are an Affected URL of at least one *Issue*-type Issue.
- `score` is the Health Score, or `null` when `internal_pages` is 0.

Where the values come from SHALL follow the Crawl State, as the Issues of `040-add-rules` do:
- `completed` or `stopped`: the derived fields of the `crawl` row that `040-add-rules`' post-crawl pass wrote, `health_score` as `score`, `health_internal_page_count` as `internal_pages` and `health_affected_page_count` as `affected_pages`.
- every other state (`running`, `failed` or `interrupted`): computed at query time with the Health Score function of `040-add-rules`, over the Affected URLs that its Issues reader computes live.

The `issues` member, and every Issue that `issues`, `issues <rule-id>` and `page <url>` show, SHALL be read through the Issues reader of `040-add-rules`, which reads the materialised Issues of a `completed` or `stopped` Crawl and computes them live in every other Crawl State.

The `issues` member SHALL be `{total, by_type_priority, top}`:
- `total` is the number of Issues.
- `by_type_priority` has exactly nine cells, `{issue_type, priority, issues, affected_count}`, in the order issue/high, issue/medium, issue/low, warning/high, warning/medium, warning/low, opportunity/high, opportunity/medium, opportunity/low. `affected_count` is the sum of the `affected_count` values of the Issues in the cell.
- `top` holds the first N Issues in the order of the `issues` Command, each with the fields of an `issues` item. N is set by `--top` (0 to 100, default 10).

#### Scenario: Health Score components
- **WHEN** a `running` Crawl has 10 Internal Pages, the live queries of *Issue*-type Rules affect 2 of them, and those of Warning-type Rules only affect 3 others
- **THEN** `health_score` is `{"score": 80, "internal_pages": 10, "affected_pages": 2}`

#### Scenario: A finished Crawl's Health Score is the stored one
- **WHEN** a `completed` Crawl's `crawl` row has `health_score` 70, `health_internal_page_count` 10 and `health_affected_page_count` 3
- **THEN** `health_score` is `{"score": 70, "internal_pages": 10, "affected_pages": 3}`

#### Scenario: No Internal Pages
- **WHEN** a Crawl has no Internal Pages
- **THEN** `health_score` is `{"score": null, "internal_pages": 0, "affected_pages": 0}`

#### Scenario: Issue counts by Issue Type and Priority
- **WHEN** a Crawl has the Issues `title-missing` (Issue Type issue, Priority high, `affected_count` 4), `h1-missing` (issue, high, 2) and `meta-description-too-long` (opportunity, low, 7)
- **THEN** `issues.total` is `3`, and the `[issues, affected_count]` pairs of the nine `issues.by_type_priority` cells, in cell order, are `[2, 6]`, `[0, 0]`, `[0, 0]`, `[0, 0]`, `[0, 0]`, `[0, 0]`, `[0, 0]`, `[0, 0]` and `[1, 7]`

#### Scenario: Top Issues
- **WHEN** a Crawl has the Issues A (warning, high, `affected_count` 50), B (issue, low, 3), C (issue, high, 1) and D (issue, high, 9)
- **AND** `spider summary --top 3` runs
- **THEN** the rule ids in `issues.top` are D, C and B, in that order

#### Scenario: Top out of range
- **WHEN** `spider summary --top 101` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: Summary JSON contract

The summary SHALL always have exactly these top-level members: `summary_version`, `crawl`, `segment`, `totals`, `status_classes`, `indexability`, `content_types`, `crawl_depth`, `response_time_ms`, `health_score`, `issues`, `segments` and `unsegmented`. A member that has no value is `null` or empty, never left out. `summary_version` SHALL be `1`. Adding a member SHALL NOT change it. Removing or renaming a member, or changing its meaning, SHALL increase it. The Report (`070-add-html-report`) SHALL be built from this same model. The `segment`, `segments` and `unsegmented` members are specified by the `segments` capability; until Segments arrive in v0.2 they are always `null`, `[]` and `null`.

#### Scenario: Top-level members
- **WHEN** `spider summary` runs against a `completed` Crawl that recorded no URLs, in a Workspace with no Segments defined
- **THEN** the output's top-level keys are exactly the thirteen members listed above, in any order

#### Scenario: Summary version
- **WHEN** `spider summary` runs
- **THEN** the output contains `"summary_version": 1`

#### Scenario: Contract on the fixture site
- **WHEN** `spider summary` runs against a `completed` Crawl of the reference pages of the local fixture site
- **THEN** the output equals the hand-written expected summary for those pages, ignoring `crawl.id`, `crawl.started_at`, `crawl.completed_at`, `crawl.tool_version` and `response_time_ms`

### Requirement: Summary for people

`spider summary` SHALL support the formats `json` and `table`. `--format table` SHALL print the summary as titled plain-text tables. Any other format SHALL be rejected with the `invalid_value` error of `010-add-workspace-and-cli-contract`, whose hint lists `json` and `table`.

#### Scenario: Table output
- **WHEN** `spider summary --format table` runs against a Crawl whose Health Score is 80
- **THEN** stdout contains a line that holds both `Health Score` and `80`

#### Scenario: CSV is refused
- **WHEN** `spider summary --format csv` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and a hint that contains `json` and `table`

### Requirement: Where filter language

The `--where` option of `pages`, `issues <rule-id>` and `export`, and every Segment definition, SHALL accept an expression in this grammar:

```
expression = or_expr
or_expr    = and_expr { "or" and_expr }
and_expr   = unary { "and" unary }
unary      = "not" unary | primary
primary    = "(" expression ")" | predicate
predicate  = column compare literal
           | column ( "~" | "!~" ) string
           | column [ "not" ] "contains" string
           | column [ "not" ] "in" "(" literal { "," literal } ")"
           | column "is" [ "not" ] "null"
compare    = "=" | "!=" | "<>" | "<" | "<=" | ">" | ">="
literal    = string | number | "true" | "false"
string     = "'" { character other than "'" | "''" } "'"
           | '"' { character other than '"' | '""' } '"'
number     = [ "-" ] digit { digit } [ "." digit { digit } ]
column     = letter { letter | digit | "_" }
```

- Keywords (`and`, `or`, `not`, `contains`, `in`, `is`, `null`, `true`, `false`) are case-insensitive. `not` binds tighter than `and`, and `and` binds tighter than `or`.
- Column names are matched case-insensitively. They are the column names of the `pages` table (`030-add-page-data`) that `spider schema` lists, or for `export` the columns of the chosen view.
- Inside a string, a quote character is written twice. Backslashes have no special meaning.
- `=`, `!=`, `<>` and `in` compare exactly; text comparison is case-sensitive. `<`, `<=`, `>` and `>=` compare numbers numerically and text by Unicode code point.
- `~` is true when the regular expression (Python `re` syntax) is found anywhere in the value. It is case-sensitive unless the pattern uses `(?i)`. `!~` is true when it is not found.
- `contains` is a case-insensitive substring test with Unicode case folding.
- `~`, `!~` and `contains` apply to the text form of any column.
- `true` and `false` compare with boolean columns only.

In v0.1 the language SHALL be the `and` of predicates of three forms: `column compare literal`, `column contains string` and `column is [not] null`. `or`, `not`, parentheses, `~`, `!~`, `in` and `not contains` arrive in v0.2; until then they are syntax errors (`invalid_where`).

#### Scenario: Comparison
- **WHEN** Pages A (status_code 200), B (404) and C (500) are filtered with `status_code >= 400`
- **THEN** the matching Pages are B and C

#### Scenario: and requires both
- **WHEN** Pages A (status_code 404, crawl_depth 1), B (404, 5) and C (200, 5) are filtered with `status_code = 404 and crawl_depth > 3`
- **THEN** the only matching Page is B

#### Scenario: and binds tighter than or
- **WHEN** Pages A (status_code 404, crawl_depth 1), B (200, 5) and C (200, 1) are filtered with `status_code = 404 or status_code = 200 and crawl_depth > 3`
- **THEN** the matching Pages are A and B

#### Scenario: Parentheses override precedence
- **WHEN** Pages A (status_code 404, crawl_depth 1), B (200, 5) and C (200, 1) are filtered with `(status_code = 404 or status_code = 200) and crawl_depth > 3`
- **THEN** the only matching Page is B

#### Scenario: not
- **WHEN** Pages A (status_code 200) and B (404) are filtered with `not status_code = 200`
- **THEN** the only matching Page is B

#### Scenario: Keywords are case-insensitive
- **WHEN** Pages A (status_code 404), B (500) and C (200) are filtered with `status_code = 404 OR status_code = 500`
- **THEN** the matching Pages are A and B

#### Scenario: Column names are case-insensitive
- **WHEN** Pages A (status_code 200) and B (404) are filtered with `STATUS_CODE = 404`
- **THEN** the only matching Page is B

#### Scenario: Regular expression
- **WHEN** Pages at `https://example.com/blog/post` and `https://example.com/shop/item` are filtered with `address ~ '/blog/'`
- **THEN** the only matching Page is `https://example.com/blog/post`

#### Scenario: Regular expressions are case-sensitive by default
- **WHEN** a Page at `https://example.com/blog/post` is filtered with `address ~ '/BLOG/'`
- **THEN** no Page matches

#### Scenario: Case-insensitive regular expression
- **WHEN** a Page at `https://example.com/blog/post` is filtered with `address ~ '(?i)/BLOG/'`
- **THEN** the Page matches

#### Scenario: Negated regular expression
- **WHEN** Pages at `https://example.com/blog/post` and `https://example.com/shop/item` are filtered with `address !~ '/blog/'`
- **THEN** the only matching Page is `https://example.com/shop/item`

#### Scenario: Backslashes reach the regular expression unchanged
- **WHEN** Pages at `https://example.com/file.pdf` and `https://example.com/filexpdf` are filtered with `address ~ '\.pdf$'`
- **THEN** the only matching Page is `https://example.com/file.pdf`

#### Scenario: Regular expression on a number column
- **WHEN** Pages A (status_code 404), B (410) and C (200) are filtered with `status_code ~ '^4'`
- **THEN** the matching Pages are A and B

#### Scenario: contains ignores case in any script
- **WHEN** Pages A (title_1 `Каталог товаров`) and B (title_1 `О компании`) are filtered with `title_1 contains 'КАТАЛОГ'`
- **THEN** the only matching Page is A

#### Scenario: not contains
- **WHEN** Pages A (title_1 `Blog home`) and B (title_1 `Shop`) are filtered with `title_1 not contains 'blog'`
- **THEN** the only matching Page is B

#### Scenario: in and not in
- **WHEN** Pages A (status_code 200), B (301) and C (404) are filtered with `status_code not in (301, 404)`
- **THEN** the only matching Page is A

#### Scenario: is null and is not null
- **WHEN** Pages A (meta_description_1 null) and B (meta_description_1 `Hello`) are filtered with `meta_description_1 is null`
- **THEN** the only matching Page is A

#### Scenario: Doubled quotes inside a string
- **WHEN** Pages A (title_1 `It's here`) and B (title_1 `Its here`) are filtered with `title_1 = 'It''s here'`
- **THEN** the only matching Page is A

#### Scenario: Double-quoted string
- **WHEN** Pages A (title_1 `It's here`) and B (title_1 `Its here`) are filtered with `title_1 = "It's here"`
- **THEN** the only matching Page is A

#### Scenario: Boolean literal
- **WHEN** rows A (a boolean column `flag` true) and B (`flag` false) are filtered with `flag = true`
- **THEN** the only matching row is A

#### Scenario: Non-ASCII literal passed on the Windows command line
- **WHEN** on Windows, `spider pages --where "title_1 contains 'café'"` runs as a real subprocess against Pages A (title_1 `Café Paris`) and B (title_1 `Tea`)
- **THEN** the output's `total` is `1` and its only item has the address of Page A

### Requirement: Null values in filters

Every predicate other than `is null` and `is not null` SHALL be false when the column value is `null`. `not` SHALL turn false into true, so every expression is either true or false for every row.

#### Scenario: A comparison excludes null values
- **WHEN** Pages A (word_count 250), B (800) and C (null) are filtered with `word_count < 300`
- **THEN** the only matching Page is A

#### Scenario: not includes null values
- **WHEN** Pages A (word_count 250), B (800) and C (null) are filtered with `not (word_count >= 300)`
- **THEN** the matching Pages are A and C

#### Scenario: Not-equal excludes null values
- **WHEN** Pages A (word_count 250), B (800) and C (null) are filtered with `word_count != 250`
- **THEN** the only matching Page is B

#### Scenario: Double negation changes nothing
- **WHEN** any valid expression `e` over a set of rows that includes null values is compared with `not not (e)`
- **THEN** both match exactly the same rows

### Requirement: Filter values fit the column type

A string literal compared with a numeric column, a number literal compared with a text column (with `=`, `!=`, `<>`, `<`, `<=`, `>`, `>=` or `in`), and `true` or `false` compared with a non-boolean column SHALL be rejected with the error code `invalid_where`, and the message SHALL name the column and its type. A regular expression that cannot be compiled SHALL be rejected with `invalid_where`, and the message SHALL quote the pattern.

#### Scenario: String compared with a number column
- **WHEN** `spider pages --where "status_code = 'abc'"` runs
- **THEN** the exit code is 2, and the error has the code `invalid_where` and a message that contains `status_code`

#### Scenario: Number compared with a text column
- **WHEN** `spider pages --where "title_1 > 5"` runs
- **THEN** the exit code is 2, and the error has the code `invalid_where` and a message that contains `title_1`

#### Scenario: Invalid regular expression
- **WHEN** `spider pages --where "address ~ '('"` runs
- **THEN** the exit code is 2, and the error has the code `invalid_where` and a message that contains `'('`

### Requirement: Filter syntax errors

An expression that does not match the grammar SHALL be rejected with the error code `invalid_where` before any query runs. The message SHALL give the 1-based character position where parsing failed. An expression nested more than 64 levels deep SHALL be rejected with `invalid_where`. The expression SHALL never reach the store as SQL text.

#### Scenario: Position of a syntax error
- **WHEN** `spider pages --where "status_code = = 200"` runs
- **THEN** the exit code is 2, and the error has the code `invalid_where` and a message that contains `position 15`

#### Scenario: SQL cannot be smuggled in
- **WHEN** `spider pages --where "address = 'x'; DROP TABLE pages"` runs
- **THEN** the error has the code `invalid_where` and a message that contains `position 14`

#### Scenario: A smuggling attempt leaves the store unchanged
- **WHEN** `spider pages --where "address = 'x'; DROP TABLE pages"` has been rejected
- **THEN** a SQL dump of the crawl store is identical to one taken before it ran

#### Scenario: Nesting limit
- **WHEN** `--where` is `status_code = 200` wrapped in 65 pairs of parentheses
- **THEN** the expression is rejected with code `invalid_where`

#### Scenario: Any input either parses or fails cleanly
- **WHEN** any string of up to 200 printable characters is given as a `--where` expression
- **THEN** the result is either a valid filter or an `invalid_where` error, and never a crash

### Requirement: Unknown names in --where, --sort and --fields

A column name in `--where` or `--sort` that the queried view does not have SHALL be rejected with the error code `unknown_column`. The message SHALL name the unknown column, `details.suggestions` SHALL list up to five of the closest valid names, closest first, and the hint SHALL mention `spider schema`. A name in `--fields` that the Command does not offer SHALL be rejected with the `unknown_field` error of `010-add-workspace-and-cli-contract`, with `details.field` and `details.available`.

#### Scenario: Unknown column in --where
- **WHEN** `spider pages --where "stauts_code = 200"` runs
- **THEN** the exit code is 2, the error has the code `unknown_column`, its `details.suggestions` starts with `status_code`, and its hint contains `spider schema`

#### Scenario: Unknown column in --sort
- **WHEN** `spider pages --sort -wordcount` runs
- **THEN** the error has the code `unknown_column`, and its `details.suggestions` starts with `word_count`

#### Scenario: Unknown field in --fields
- **WHEN** `spider pages --fields adress,title_1` runs
- **THEN** the exit code is 2, and the error has the code `unknown_field` and `details.field` `"adress"`

### Requirement: Page listing

`spider pages` SHALL return the paging envelope of `010-add-workspace-and-cli-contract` (`{total, items, next_cursor}`, with `--fields`, `--limit` and `--cursor`), with one item per Page of the Crawl that matches `--where` and `--segment`. `total` counts every matching Page.
- Without `--fields`, each item SHALL hold exactly the default fields `address`, `status_code`, `indexability`, `indexability_status`, `title_1` and `crawl_depth`.
- The available fields SHALL be the columns of the `pages` table (`030-add-page-data`) in the order `spider schema` lists them, followed, from v0.2, by `segment`. `--fields all` selects all of them.

#### Scenario: Default fields
- **WHEN** `spider pages` runs against a Crawl with one Page
- **THEN** the keys of its item are exactly `address`, `status_code`, `indexability`, `indexability_status`, `title_1` and `crawl_depth`

#### Scenario: Total counts every match
- **WHEN** `spider pages --limit 50` runs against a Crawl with 120 Pages
- **THEN** `total` is `120`, `items` holds 50 items, and `next_cursor` is not `null`

#### Scenario: Selected fields
- **WHEN** `spider pages --fields address,word_count` runs against a Page at `https://example.com/` with word_count 812
- **THEN** its item is `{"address": "https://example.com/", "word_count": 812}`

#### Scenario: All fields
- **WHEN** `spider pages --fields all` runs
- **THEN** the keys of each item are every `pages` column that `spider schema` lists, in that order

#### Scenario: Filtered listing
- **WHEN** `spider pages --where "status_code = 404"` runs against a Crawl with 5 Pages, 2 of which have status code 404
- **THEN** `total` is `2`

#### Scenario: Non-ASCII titles on the Windows console
- **WHEN** on Windows, `spider pages --fields title_1` runs as a real subprocess against a Page whose title_1 is `Привет, мир`
- **THEN** stdout is valid UTF-8 and decodes to JSON whose item has `"title_1": "Привет, мир"`

### Requirement: Sorting

`--sort` SHALL take a comma-separated list of keys and SHALL be repeatable, each repetition adding further keys in the order given. Each key is a column name or, from v0.2, `segment`, and a leading `-` sorts that key descending. The default order SHALL be `address` ascending. Null values SHALL sort last in both directions, and text SHALL sort by Unicode code point. Ties SHALL be broken by `address`, so walking the pages through `next_cursor` returns every Page that existed at the first call exactly once, even when the Crawl stores more Pages in between. A malformed `--sort` value SHALL be rejected with the error code `invalid_sort`.

#### Scenario: Several keys, one descending
- **WHEN** Pages A (crawl_depth 2, word_count 100), B (1, 50) and C (2, 300) are listed with `--sort crawl_depth,-word_count`
- **THEN** the order is B, C, A

#### Scenario: Repeated flag
- **WHEN** Pages A (crawl_depth 2, word_count 100), B (1, 50) and C (2, 300) are listed with `--sort crawl_depth --sort -word_count`
- **THEN** the order is B, C, A

#### Scenario: Nulls sort last when descending
- **WHEN** Pages A (word_count null), B (10) and C (20) are listed with `--sort -word_count`
- **THEN** the order is C, B, A

#### Scenario: Nulls sort last when ascending
- **WHEN** Pages A (word_count null), B (10) and C (20) are listed with `--sort word_count`
- **THEN** the order is B, C, A

#### Scenario: Default order
- **WHEN** Pages at `https://example.com/c`, `https://example.com/a` and `https://example.com/b` are listed without `--sort`
- **THEN** the order is `https://example.com/a`, `https://example.com/b`, `https://example.com/c`

#### Scenario: Paging is stable while the Crawl writes
- **WHEN** 7 Pages with crawl_depth 1 are listed with `--sort crawl_depth --limit 3`
- **AND** 2 new Pages are stored after the first call, before the remaining pages are read through `next_cursor`
- **THEN** each of the 7 original Pages appears exactly once across the pages

#### Scenario: Malformed sort
- **WHEN** `spider pages --sort ","` runs
- **THEN** the exit code is 2, and the error has the code `invalid_sort`

### Requirement: Cursors are bound to the query

Cursors returned by `pages` and `issues <rule-id>` SHALL follow the cursor rule of `010-add-workspace-and-cli-contract`. The Crawl, `--where`, `--sort` and `--segment` SHALL count as filters that the cursor is bound to, so a cursor used with any other value of them SHALL fail with `invalid_cursor`.

#### Scenario: A cursor is reused with another filter
- **WHEN** a `next_cursor` from `spider pages --where "status_code = 200"` is passed to `spider pages --where "status_code = 404" --cursor <that cursor>`
- **THEN** the exit code is 2, and the error has the code `invalid_cursor`

#### Scenario: A cursor is reused with another Segment
- **WHEN** a `next_cursor` from `spider pages --segment blog` is passed to `spider pages --segment shop --cursor <that cursor>`
- **THEN** the exit code is 2, and the error has the code `invalid_cursor`

### Requirement: Single URL detail

`spider page <url>` SHALL return a JSON object with these members:
- `url`: the recorded address.
- `segment`: the name of the URL's Segment, or `null`; always `null` until Segments arrive in v0.2.
- `columns`: every column of the URL's `pages` row, named as `spider schema` names it.
- `issues`: every Issue that has this URL as an Affected URL, read through the Issues reader of `040-add-rules`, as `{rule_id, category, issue_type, priority, description, detail}`, in the order of the `issues` Command.
- `redirect_chain`: the hops of the URL's Redirect Chain as `022-add-fetch-policy` records them, as `{url, status_code}` in order, ending with the final destination. It is empty when the URL did not redirect.
- `link_counts`: the URL's `inlinks`, `unique_inlinks`, `outlinks`, `unique_outlinks` and `external_outlinks`, as defined by `030-add-page-data`, plus `partial`, which is `true` for a Section Crawl.
- `html_stored`: whether raw HTML is stored for the URL; always `false` until HTML storage arrives in v0.2.

The given URL SHALL be normalised with the URL normalisation of `020-add-crawl-core`, which removes the fragment and lowercases the scheme and host, and then matched against the recorded URLs. A URL without a `pages` row in the Crawl SHALL be rejected with the error code `url_not_found`. `details.suggestions` SHALL list up to five recorded addresses closest to it.

#### Scenario: Redirect Chain
- **WHEN** `https://example.com/old` answered 301 to `https://example.com/mid`, which answered 302 to `https://example.com/new`, which answered 200
- **AND** `spider page https://example.com/old` runs
- **THEN** `redirect_chain` is `[{"url": "https://example.com/old", "status_code": 301}, {"url": "https://example.com/mid", "status_code": 302}, {"url": "https://example.com/new", "status_code": 200}]`

#### Scenario: No redirect
- **WHEN** `spider page https://example.com/new` runs for a URL that answered 200 directly
- **THEN** `redirect_chain` is `[]`

#### Scenario: Issues of the URL
- **WHEN** `https://example.com/a` is an Affected URL of the Issues `h1-missing` (issue, high) and `meta-description-too-long` (opportunity, low)
- **AND** `spider page https://example.com/a` runs
- **THEN** the `rule_id` values of `issues` are `h1-missing` and `meta-description-too-long`, in that order

#### Scenario: Link counts in a Section Crawl
- **WHEN** `spider page https://example.com/blog/` runs against a Section Crawl in which that Page has 3 Inlinks, 2 Unique Inlinks, 10 Outlinks, 8 Unique Outlinks and 1 External Outlink
- **THEN** `link_counts` is `{"inlinks": 3, "unique_inlinks": 2, "outlinks": 10, "unique_outlinks": 8, "external_outlinks": 1, "partial": true}`

#### Scenario: Fragment and host case are ignored
- **WHEN** the Crawl recorded `https://example.com/about` and `spider page https://EXAMPLE.com/about#team` runs
- **THEN** `url` is `https://example.com/about`

#### Scenario: Unknown URL
- **WHEN** the Crawl recorded `https://example.com/about` and `spider page https://example.com/abuot` runs
- **THEN** the exit code is 4, the error has the code `url_not_found`, and its `details.suggestions` starts with `https://example.com/about`

### Requirement: Raw HTML of a Page

`spider page <url> --html` SHALL add two members to the output: `html`, the stored HTML of the Page (`030-add-page-data`) decoded as text, and `encoding`, the character encoding it was decoded with. Without `--html`, the output SHALL have neither member. When no raw HTML is stored for the URL, the command SHALL fail with the error code `html_not_stored`. The hint SHALL explain that raw HTML is stored only for Crawls started with `crawl --store-html`. `--html` and `--headers` SHALL combine.

#### Scenario: Stored HTML
- **WHEN** the stored HTML of `https://example.com/` is `<html><body>Hi</body></html>`, decoded as `utf-8`
- **AND** `spider page https://example.com/ --html` runs
- **THEN** the output contains `"html": "<html><body>Hi</body></html>"` and `"encoding": "utf-8"`

#### Scenario: HTML decoded from windows-1251
- **WHEN** the stored HTML of `https://example.com/ru` is the windows-1251 encoding of `<p>Привет</p>`, with the encoding `windows-1251`
- **AND** `spider page https://example.com/ru --html` runs
- **THEN** the output contains `"html": "<p>Привет</p>"` and `"encoding": "windows-1251"`

#### Scenario: No html member by default
- **WHEN** `spider page https://example.com/` runs without `--html`
- **THEN** the output has neither an `html` nor an `encoding` key

#### Scenario: HTML and headers together
- **WHEN** raw HTML and response headers are stored for `https://example.com/`, and `spider page https://example.com/ --html --headers` runs
- **THEN** the output has the keys `html`, `encoding` and `headers`

#### Scenario: HTML on the Windows console
- **WHEN** on Windows, `spider page https://example.com/ru --html` runs as a real subprocess with stdout piped
- **THEN** stdout is valid UTF-8 and decodes to JSON whose `html` is `<p>Привет</p>`

#### Scenario: HTML not stored
- **WHEN** a Crawl was run without `--store-html` and `spider page https://example.com/ --html` runs
- **THEN** the exit code is 4, and the error has the code `html_not_stored` and a hint that contains `--store-html`

### Requirement: Response headers of a URL

`spider page <url> --headers` SHALL add a `headers` member: the response headers that `022-add-fetch-policy` recorded for the URL, as a list of `{name, value}` in the order they were received, with repeated headers kept. Cookie values appear as `022-add-fetch-policy` stores them, redacted. Without `--headers`, the output SHALL have no `headers` member. When the Crawl recorded no response headers for the URL, the command SHALL fail with the error code `headers_not_stored`.

#### Scenario: Repeated headers are kept
- **WHEN** `https://example.com/` answered with the headers `Content-Type: text/html`, `Link: </a.css>; rel=preload` and `Link: </b.js>; rel=preload`, in that order
- **AND** `spider page https://example.com/ --headers` runs
- **THEN** `headers` is `[{"name": "Content-Type", "value": "text/html"}, {"name": "Link", "value": "</a.css>; rel=preload"}, {"name": "Link", "value": "</b.js>; rel=preload"}]`

#### Scenario: Cookie values are not shown
- **WHEN** the fixture page `/cookie` answers with `Set-Cookie: session=abc123`, a Crawl of the local fixture site stores it, and `spider page <fixture>/cookie --headers` runs
- **THEN** `headers` has an entry named `Set-Cookie` whose value does not contain `abc123`

#### Scenario: No headers member by default
- **WHEN** `spider page https://example.com/` runs without `--headers`
- **THEN** the output has no `headers` key

#### Scenario: Headers not recorded
- **WHEN** the Crawl recorded no response headers for `https://example.com/` and `spider page https://example.com/ --headers` runs
- **THEN** the exit code is 4, and the error has the code `headers_not_stored`

### Requirement: Issue list

`spider issues` SHALL return the paging envelope with one item per Issue: `{rule_id, category, issue_type, priority, affected_count, description}`.
- `category` is the Rule category id of `040-add-rules`.
- Issue Types are `issue`, `warning` and `opportunity`. Priorities are `high`, `medium` and `low`.
- `affected_count` is the number of the Issue's Affected URLs.
- `description` is the Rule's description.

The Issues SHALL be read through the Issues reader of `040-add-rules`, so a Crawl that is still `running`, or ended without its post-crawl pass, shows the Issues its stored rows give now. Only Rules with at least one Affected URL SHALL appear. The order SHALL be by Issue Type (issue, warning, opportunity), then by Priority (high, medium, low), then by `affected_count` descending, then by `rule_id`.

`--type`, `--priority` and `--category` SHALL each take comma-separated values, case-insensitively, and SHALL be repeatable. The values of one flag are alternatives, and different flags must all match. An unknown value SHALL be rejected with the error code `invalid_value`, whose `details.accepted` lists the accepted values.

#### Scenario: Order
- **WHEN** a Crawl has the Issues A (warning, high, `affected_count` 50), B (issue, low, 3), C (issue, high, 1) and D (issue, high, 9)
- **AND** `spider issues` runs
- **THEN** the `rule_id` values of the items are D, C, B and A, in that order

#### Scenario: Item fields
- **WHEN** a Crawl's only Issue is `title-missing` in category `titles` (issue, high) with 4 Affected URLs
- **AND** `spider issues` runs
- **THEN** its item contains `"rule_id": "title-missing"`, `"category": "titles"`, `"issue_type": "issue"`, `"priority": "high"` and `"affected_count": 4`, and its `description` equals the description that `spider rules show title-missing` prints

#### Scenario: Filters combine
- **WHEN** a Crawl has the Issues A (warning, high), B (issue, low), C (issue, high) and D (opportunity, high)
- **AND** `spider issues --type issue,warning --priority high` runs
- **THEN** the `rule_id` values of the items are C and A, in that order

#### Scenario: Filter by category
- **WHEN** a Crawl has the Issues `title-missing` (category `titles`) and `h1-missing` (category `headings`)
- **AND** `spider issues --category headings` runs
- **THEN** the only item has the `rule_id` `h1-missing`

#### Scenario: Issues of a running Crawl are computed live
- **WHEN** a `running` Crawl has stored the analysed Page `https://example.com/a` without a `<title>`, and its `affected_urls` holds no rows
- **AND** `spider issues` runs
- **THEN** an item has the `rule_id` `title-missing` and `"affected_count": 1`

#### Scenario: Issues of a fixture Crawl on every OS
- **WHEN** on Windows, macOS and Linux, `spider crawl {site}/e2e/` runs as a real subprocess, where `/e2e/` has a title and an `<h1>` and links to `/e2e/notitle`, which has an `<h1>` and no `<title>`, and to `/e2e/gone`, which responds 404
- **AND** `spider issues` then runs as a real subprocess
- **THEN** its items include `internal-4xx` and `title-missing`, each with `"affected_count": 1`

#### Scenario: Unknown Issue Type
- **WHEN** `spider issues --type critical` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and `details.accepted` `["issue", "warning", "opportunity"]`

### Requirement: Issue detail

`spider issues <rule-id>` SHALL return `{rule, total, items, next_cursor}`:
- `rule` is `{rule_id, category, issue_type, priority, description, why_it_matters, how_to_fix, thresholds, reproduce_sql}`, taken from the Crawl's `rules` table (`040-add-rules`). `thresholds` maps each threshold name to the value that applied to the Crawl, and `reproduce_sql` is the Rule's query, which `spider sql` runs.
- The items are the Issue's Affected URLs, read through the Issues reader of `040-add-rules`. Without `--fields`, each item SHALL be `{url, detail}`, where `detail` is the JSON object of measured values that `040-add-rules` recorded for that Affected URL, or `null`. The available fields are `url`, `detail`, the `pages` columns and `segment`. Page columns and `segment` are `null` for an Affected URL without a `pages` row.
- The default order SHALL be `unique_inlinks` descending, then `url`. `--where`, `--sort`, `--limit`, `--cursor` and `--segment` SHALL work as they do for `pages`.

A Rule that has no Affected URL in the Crawl SHALL return `total` 0 and empty `items`. An unknown rule id SHALL be rejected with the error code `rule_not_found` of `040-add-rules`. The hint SHALL mention `spider rules list`, and `details.suggestions` SHALL list the closest rule ids.

#### Scenario: Most-linked Affected URLs first
- **WHEN** the Issue `title-too-long` has the Affected URLs A (unique_inlinks 5), B (12) and C (null)
- **AND** `spider issues title-too-long` runs
- **THEN** the `url` values of the items are B, A and C, in that order

#### Scenario: Thresholds recorded for the Crawl
- **WHEN** a Crawl ran with the threshold `max_chars` of the Rule `title-too-long` set to 70
- **AND** `spider issues title-too-long` runs
- **THEN** `rule.thresholds` is `{"max_chars": 70}`

#### Scenario: Guidance of the Rule
- **WHEN** `spider issues title-too-long` runs
- **THEN** `rule.how_to_fix` equals the `how_to_fix` text that `spider rules show title-too-long` prints

#### Scenario: The reproducing query of the Rule
- **WHEN** `spider issues title-missing` runs
- **THEN** `rule.reproduce_sql` equals the `reproduce_sql` of the Crawl's `rules` row for `title-missing`

#### Scenario: Detail of an Affected URL
- **WHEN** the Issue `internal-4xx` has the single Affected URL `https://example.com/gone`, recorded with `detail` `{"status_code": 404}`
- **AND** `spider issues internal-4xx` runs
- **THEN** `items` is `[{"url": "https://example.com/gone", "detail": {"status_code": 404}}]`

#### Scenario: Page columns for Affected URLs
- **WHEN** the Issue `title-too-long` has the single Affected URL `https://example.com/a`, whose title_1_length is 81
- **AND** `spider issues title-too-long --fields url,title_1_length` runs
- **THEN** `items` is `[{"url": "https://example.com/a", "title_1_length": 81}]`

#### Scenario: A Rule that did not fire
- **WHEN** no Page of the Crawl is an Affected URL of the Rule `h1-missing`
- **AND** `spider issues h1-missing` runs
- **THEN** the exit code is 0, `total` is `0` and `items` is `[]`

#### Scenario: Unknown rule id
- **WHEN** `spider issues title-mising` runs
- **THEN** the exit code is 4, the error has the code `rule_not_found`, and its `details.suggestions` starts with `title-missing`

### Requirement: Read-only SQL

`spider sql "<query>"` SHALL run exactly one statement that starts with `SELECT` or `WITH` and only reads, on the read-only access of `015-add-crawl-store`. Anything else SHALL be refused with the error code `sql_not_allowed` without changing the store. That covers:
- any other statement, including INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, ATTACH, DETACH, PRAGMA, VACUUM, REINDEX, ANALYZE and transaction statements
- a `WITH` statement that modifies data
- more than one statement
- loading an extension

#### Scenario: A SELECT runs
- **WHEN** `spider sql "SELECT 1 AS one"` runs
- **THEN** the output contains `"columns": ["one"]` and `"rows": [[1]]`

#### Scenario: Writes are refused
- **WHEN** `spider sql "DELETE FROM pages"` runs
- **THEN** the exit code is 2, and the error has the code `sql_not_allowed`

#### Scenario: A refused write changes nothing
- **WHEN** `spider sql "DELETE FROM pages"` has been refused
- **THEN** a SQL dump of the crawl store is identical to one taken before it ran

#### Scenario: A WITH that writes is refused
- **WHEN** `spider sql "WITH x AS (SELECT 1) DELETE FROM pages"` runs
- **THEN** the error has the code `sql_not_allowed`

#### Scenario: Two statements are refused
- **WHEN** `spider sql "SELECT 1; SELECT 2"` runs
- **THEN** the error has the code `sql_not_allowed`

#### Scenario: PRAGMA is refused
- **WHEN** `spider sql "PRAGMA journal_mode=DELETE"` runs
- **THEN** the error has the code `sql_not_allowed`

#### Scenario: ATTACH is refused
- **WHEN** `spider sql "ATTACH DATABASE 'other.db' AS other"` runs
- **THEN** the error has the code `sql_not_allowed`, and no file named `other.db` exists afterwards

#### Scenario: Loading an extension is refused
- **WHEN** `spider sql "SELECT load_extension('evil')"` runs
- **THEN** the error has the code `sql_not_allowed`

### Requirement: SQL results

`spider sql` SHALL return `{columns, rows, row_count, truncated, limit}`:
- `columns` lists the result column names in order, duplicates included.
- `rows` holds each row as an array in column order.
- `row_count` is the number of rows returned. `truncated` is `true` when the query had more rows than `limit`.
- `limit` defaults to 1000 and is set by `--limit` (1 to 100,000).
- A BLOB value SHALL be returned as `{"blob_bytes": <length>}`.

#### Scenario: Default row limit
- **WHEN** `spider sql "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 1500) SELECT i FROM n"` runs
- **THEN** the output contains `"row_count": 1000`, `"truncated": true` and `"limit": 1000`

#### Scenario: Custom row limit
- **WHEN** the same query runs with `--limit 5`
- **THEN** `rows` is `[[1], [2], [3], [4], [5]]` and `truncated` is `true`

#### Scenario: Duplicate column names
- **WHEN** `spider sql "SELECT 1 AS a, 2 AS a"` runs
- **THEN** the output contains `"columns": ["a", "a"]` and `"rows": [[1, 2]]`

#### Scenario: BLOB values
- **WHEN** `spider sql "SELECT x'00010203' AS b"` runs
- **THEN** `rows` is `[[{"blob_bytes": 4}]]`

### Requirement: SQL errors, timeout and query files

A query that SQLite rejects SHALL fail with the error code `sql_error`, and the message SHALL contain SQLite's message. For an unknown table or column, `details.suggestions` SHALL list the closest names, and the hint SHALL mention `spider schema`. A query that runs longer than `--timeout` seconds (default 30) SHALL be interrupted and fail with the error code `sql_timeout`. `--file <path>` SHALL read the query from a UTF-8 file, with or without a byte-order mark. Giving both a query argument and `--file` SHALL be rejected with the `usage_error` of `010-add-workspace-and-cli-contract`.

#### Scenario: Unknown column
- **WHEN** `spider sql "SELECT adress FROM pages"` runs
- **THEN** the exit code is 2, the error has the code `sql_error` and a message that contains `no such column: adress`, and its `details.suggestions` starts with `address`

#### Scenario: Timeout
- **WHEN** `spider sql --timeout 1 "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT count(*) FROM n"` runs
- **THEN** the exit code is 1, and the error has the code `sql_timeout`

#### Scenario: Query file with a byte-order mark on Windows
- **WHEN** on Windows, a file `q.sql` holds a UTF-8 byte-order mark followed by `SELECT 'Привет' AS t`
- **AND** `spider sql --file q.sql` runs as a real subprocess
- **THEN** `rows` is `[["Привет"]]`

#### Scenario: Query given twice
- **WHEN** `spider sql "SELECT 1" --file q.sql` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

### Requirement: Export views

`spider export <view>` SHALL support these views:

| View | One row per | Columns |
|---|---|---|
| `pages` | Page | the `pages` columns that `spider schema` lists, then `segment` |
| `links` | row of the `links` table (`030-add-page-data`) | `source_url` and `target_url` (the addresses of `source_url_id` and `target_url_id`), then the other `links` columns in `spider schema` order |
| `resources` | Resource | `url`, `type`, `is_internal`, `fetch_state`, `status_code`, `fetch_error`, `content_type`, `size_bytes`, `transferred_bytes`, `response_time_ms`, `inlinks` |
| `issues` | Issue | `rule_id`, `category`, `issue_type`, `priority`, `affected_count`, `description` |
| `affected-urls` | Issue and Affected URL pair | `rule_id`, `category`, `issue_type`, `priority`, `url`, `detail`, `segment` |

A Resource is a row of the `urls` table (`020-add-crawl-core`) that meets both conditions:
- it is the target of at least one `links` row whose `type` is `image`, `css`, `javascript`, `video`, `audio` or `media`
- it has no `pages` row

Its columns come from its `urls` row, except two:
- `type` is the `type` of its first such Link, by source row and `ordinal`
- `inlinks` is the number of `links` rows that target it

Options:
- `--fields` SHALL select and order columns.
- `--where` SHALL filter on the view's columns.
- `--sort` SHALL work as it does for `pages`. The defaults are:
  - `address` for `pages`
  - `url` for `resources`
  - the Issue order for `issues`
  - the Issue order, then `url`, for `affected-urls`
  - source address, then `ordinal`, for `links`
- `--segment` SHALL restrict the rows:
  - `pages`: the Segment's Pages
  - `links`: Links whose source is a Page of the Segment
  - `resources`: Resources that a Page of the Segment links to
  - `issues`: `affected_count` taken within the Segment, as for `issues --segment`
  - `affected-urls`: Affected URLs that are Pages of the Segment
- An unknown view SHALL be rejected with the error code `unknown_view`, whose `details.accepted` lists the views.

#### Scenario: Issues view
- **WHEN** a Crawl's only Issue is `title-missing` (category `titles`, issue, high) with 4 Affected URLs
- **AND** `spider export issues` runs
- **THEN** stdout is one line whose JSON object has the `rule_id` `title-missing` and the `affected_count` `4`

#### Scenario: Affected URLs of one Rule
- **WHEN** the Issue `title-missing` has 2 Affected URLs and the Issue `h1-missing` has 3
- **AND** `spider export affected-urls --where "rule_id = 'title-missing'"` runs
- **THEN** stdout has 2 lines, and each has the `rule_id` `title-missing`

#### Scenario: Link rows name their URLs
- **WHEN** the Page `https://example.com/` has one `hyperlink` Link to `https://example.com/about`
- **AND** `spider export links --fields source_url,target_url,type` runs
- **THEN** stdout is the bytes of `{"source_url":"https://example.com/","target_url":"https://example.com/about","type":"hyperlink"}\n`

#### Scenario: Links of a Segment
- **WHEN** the Segment `blog` holds the Page `https://example.com/blog/a`, which has 2 Outlinks, and the unsegmented Page `https://example.com/` has 5 Outlinks
- **AND** `spider export links --segment blog` runs
- **THEN** stdout has 2 lines

#### Scenario: Resource columns
- **WHEN** the Page `https://example.com/` has two `image` Links to `https://example.com/logo.png`, which answered 200 with a 2,048-byte `image/png` body
- **AND** `spider export resources --fields url,type,status_code,content_type,size_bytes,inlinks` runs
- **THEN** stdout is the bytes of `{"url":"https://example.com/logo.png","type":"image","status_code":200,"content_type":"image/png","size_bytes":2048,"inlinks":2}\n`

#### Scenario: A Page is not a Resource
- **WHEN** the Page `https://example.com/` has an `image` Link to `https://example.com/banner`, which returned HTML and has a `pages` row
- **AND** `spider export resources` runs
- **THEN** stdout is empty

#### Scenario: Resources of a Segment
- **WHEN** the Page `https://example.com/blog/a` of the Segment `blog` links to the image `https://example.com/img/a.png`, and the unsegmented Page `https://example.com/` links to `https://example.com/img/b.png`
- **AND** `spider export resources --segment blog --fields url` runs
- **THEN** stdout is the bytes of `{"url":"https://example.com/img/a.png"}\n`

#### Scenario: Unknown view
- **WHEN** `spider export page` runs
- **THEN** the exit code is 2, and the error has the code `unknown_view` and `details.accepted` `["pages", "links", "resources", "issues", "affected-urls"]`

### Requirement: Export formats

`export` SHALL support the formats `jsonl`, the default, as `010-add-workspace-and-cli-contract` defines it, and `csv`, as the requirement "CSV format" of this change's `cli-contract` spec defines it:
- `jsonl` writes one compact JSON object per row, with keys in column order.
- `csv` follows the requirement "CSV policy" of this change's `cli-contract` spec, including its BOM, `--no-bom`, CRLF and formula neutralisation.

Any other format SHALL be rejected with the `invalid_value` error of `010-add-workspace-and-cli-contract`, whose hint lists `jsonl` and `csv`.

#### Scenario: JSONL keeps nulls
- **WHEN** a Page at `https://example.com/` has no word count
- **AND** `spider export pages --fields address,word_count` runs
- **THEN** stdout is the bytes of `{"address":"https://example.com/","word_count":null}\n`

#### Scenario: CSV follows the CSV policy
- **WHEN** a Page at `https://example.com/` has the title_1 `Café, "best"`
- **AND** `spider export pages --fields address,title_1 --format csv` runs
- **THEN** stdout is the UTF-8 bytes of a byte-order mark followed by `address,title_1\r\nhttps://example.com/,"Café, ""best"""\r\n`

#### Scenario: Export is a rows Command
- **WHEN** `spider commands --format json` runs
- **THEN** the entry for `export` has the output kind `rows`

#### Scenario: Unsupported format
- **WHEN** `spider export pages --format table` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and a hint that contains `jsonl` and `csv`

### Requirement: Export streams its rows

`export` SHALL write each row as soon as it is read, to stdout or, with `-o`, to the file as the requirement "Writing output to a file with -o" of this change's `cli-contract` spec defines. Peak memory while exporting 200,000 Pages SHALL be no more than 50 MB above the peak while exporting 1,000 Pages.

#### Scenario: Rows go to the -o file
- **WHEN** `spider export pages --fields address -o pages.jsonl` runs against a Crawl with 2 Pages
- **THEN** stdout is empty, and `pages.jsonl` has 2 lines

#### Scenario: Bounded memory
- **WHEN** a Crawl with 200,000 Pages and a Crawl with 1,000 Pages are each exported with `spider export pages --format csv`
- **THEN** the larger export's peak memory is no more than 50 MB above the smaller one's

#### Scenario: Export leaves the store unchanged
- **WHEN** `spider export pages` runs against a `completed` Crawl
- **THEN** a SQL dump of the crawl store taken afterwards is identical to one taken before it ran

#### Scenario: No doubled carriage returns on the Windows console
- **WHEN** on Windows, `spider export pages --format csv` runs as a real subprocess writing to a pipe
- **THEN** stdout contains `\r\n` and never `\r\r\n`

### Requirement: Query error codes

Query Commands SHALL report failures as the stderr diagnostics of `010-add-workspace-and-cli-contract`, with nothing on stdout, and SHALL exit with the exit code of the error's class. They define these codes:

| Code | Exit code (class) |
|---|---|
| `invalid_where`, `unknown_column`, `invalid_sort`, `unknown_segment`, `unknown_view`, `sql_not_allowed`, `sql_error` | 2 (usage) |
| `url_not_found`, `html_not_stored`, `headers_not_stored` | 4 (not found) |
| `sql_timeout` | 1 (failed) |

They also use these codes from other changes:
- `010-add-workspace-and-cli-contract`: `usage_error`, `invalid_value`, `invalid_cursor`, `unknown_field` and `settings_invalid`
- this change's `cli-contract` spec: `output_not_writable`
- `015-add-crawl-store`: `crawl_not_found`
- `040-add-rules`: `rule_not_found`

Every error from these Commands SHALL have a non-empty hint. An error that suggests names SHALL list them in `details.suggestions`, closest first. An error about a choice, such as a Segment name, a view, an Issue Type or a Priority, SHALL list every accepted value in `details.accepted`.

#### Scenario: Error shape
- **WHEN** `spider pages --where "("` runs
- **THEN** the exit code is 2, stdout is empty, and the last line of stderr is a JSON object with `"level": "error"`, `"code": "invalid_where"`, a non-empty `message` and a non-empty `hint`

#### Scenario: Not-found class
- **WHEN** `spider page https://example.com/nowhere` runs against a Crawl that did not record that URL
- **THEN** the exit code is 4

#### Scenario: Accepted values in details
- **WHEN** `spider.toml` defines the Segments `blog` and then `shop`, and `spider pages --segment blgo` runs
- **THEN** the error's `details.accepted` is `["blog", "shop"]`
