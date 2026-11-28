# Rules

A Rule defines a deterministic condition on Crawl data and provides fixed guidance on what it
means, why it matters and how to fix it. When a Rule fires in a Crawl, it produces an Issue with
the URLs it affects. Each of those URLs is an Affected URL. [Glossary](../CONTEXT.md#analysis)

`linx rules list` and `linx rules show` describe the built-in catalogue with the thresholds
and enabled state configured in the current Workspace. They work without a Crawl. Reading the
catalogue does not run the Rules or tell you which URLs are affected.

See the [planned v0.1 Rules](../ROADMAP.md#the-v01-rules) for release scope.

## Issue Type and Priority

Issue Type describes the nature of the Issue. The CLI prints one of these values.

| Issue Type | Meaning |
|---|---|
| `issue` | A definite defect, such as a missing Page title. |
| `warning` | Something to check that can be intentional. |
| `opportunity` | Something that could be improved, such as a long Page title. |

Priority is the urgency of the fix, expressed as `high`, `medium` or `low`.

## Health Score

The Health Score is `floor(100 × (N − A) ÷ N)`. **N** counts Internal Pages, meaning all
rows in `pages` regardless of HTTP status. **A** counts the distinct Internal Pages that are
Affected URLs of an enabled Rule whose Issue Type is `issue` in that Crawl's `rules` table.
Each such Page counts once, even if several Rules affect it. Warnings, Opportunities,
Priority and findings on Resources without a Page row leave the score unchanged.

The Issues Pass writes these derived fields on the [`crawl` row](schema.md#table-crawl)
after it writes the Affected URLs.

| Field | Value |
|---|---|
| `health_score` | Integer from 0 to 100, or SQL NULL when N is 0. |
| `health_internal_page_count` | N. |
| `health_affected_page_count` | A. |
| `health_calculated_at` | Timestamp from the clock used by the Issues Pass. |

All four fields are NULL before the first Issues Pass. A resumed Crawl keeps the previous
values until its next Issues Pass recalculates them.

For Segment Health, the planned query Commands (`050`) and HTML Report (`070`) share the Store
function `openlinx.store.health.health_for_pages`. They pass a query selecting the Segment's URL ids
as `page_ids`. The function restricts both counts to the Internal Pages in that selection.
In the same read snapshot as the Issues reader, the default source is the materialised
`affected_urls`. When the reader evaluates Issues live, the caller passes its live SQL
source as `affected`, with columns `url_id` and `rule_id`. An empty Segment has zero counts
and a NULL score.

## Rules evaluated by a Crawl

The response-code Rules belong to `response_codes`, and the `http-url` Rule belongs to
`security`. Rules in both categories use the `internal_urls` population.

| Rule id | Issue Type | Priority | Fires when | `detail` |
|---|---|---|---|---|
| `internal-4xx` | `issue` | `high` | An Internal URL has a recorded HTTP status from 400 through 499. | JSON object with `status_code` |
| `internal-5xx` | `issue` | `high` | An Internal URL has a recorded HTTP status from 500 through 599. | JSON object with `status_code` |
| `internal-no-response` | `issue` | `high` | An Internal URL has `fetch_state = 'error'` and a recorded `fetch_error` other than `record_failed`. | JSON object with `error`, the recorded `fetch_error` |
| `internal-blocked-by-robots-txt` | `warning` | `medium` | An Internal URL has `blocked_by_robots_txt` set to 1 because robots.txt disallows it for the Crawl's robots user-agent token, including with `--ignore-robots`. | SQL `NULL` |
| `internal-3xx` | `warning` | `low` | An Internal URL has a recorded HTTP status from 300 through 399. | JSON object with `status_code` and `redirect_url`, the absolute Internal or External URL referenced by `redirect_url_id` or JSON `null` when no target was recorded. |
| `redirect-chain` | `warning` | `medium` | An Internal URL's Redirect Chain exceeds its recorded `max_hops` threshold (default 1 hop). | JSON object with `hops` and the absolute `final_url` where the walk stopped |
| `redirect-loop` | `issue` | `high` | An Internal URL has `in_redirect_loop` set to 1. | JSON object with `hops`, the number of distinct URLs in that loop, including any External URLs. A self-redirect counts as one URL. |
| `http-url` | `warning` | `high` | An Internal URL with scheme `http` has a recorded response status from 200 through 299. A redirect from HTTP to HTTPS falls outside that range. | JSON object with `status_code` |
| `title-missing` | `issue` | `high` | An analysed Page has no `<title>` or its first `<title>` is empty. | SQL `NULL` |
| `title-duplicate` | `warning` | `medium` | An analysed, Indexable Page shares its non-empty first title with another analysed, Indexable Page. The comparison is case-sensitive. | JSON object with `title_1` and `pages`, the number of Pages sharing the title |
| `title-too-long` | `opportunity` | `medium` | An analysed Page's first title exceeds its recorded `max_chars` limit (default 60). | JSON object with `length`, the measured character count |
| `title-too-short` | `opportunity` | `low` | A Page's first title has at least one character and fewer than its recorded `min_chars` (default 30). | JSON object with `length` |
| `title-multiple` | `issue` | `medium` | A Page has more than one `<title>`. | JSON object with `count` |
| `title-same-as-h1` | `opportunity` | `low` | A Page's first title is non-empty and equals its first `<h1>`. The comparison is case-sensitive. | SQL `NULL` |
| `meta-description-missing` | `opportunity` | `medium` | An analysed Page has no meta description or its first meta description is empty. | SQL `NULL` |
| `meta-description-duplicate` | `opportunity` | `low` | An Indexable Page shares its non-empty first meta description with another Indexable Page. The comparison is case-sensitive. | JSON object with `meta_description_1` and `pages`, the number of Pages in the group |
| `meta-description-too-long` | `opportunity` | `low` | A Page's first meta description exceeds either recorded limit, `max_chars` (default 155) or `max_pixels` (default 985). | JSON object with `length` and `width_px` |
| `meta-description-too-short` | `opportunity` | `low` | A Page's first meta description has at least one character and fewer than its recorded `min_chars` (default 70). | JSON object with `length` |
| `meta-description-multiple` | `warning` | `low` | A Page has more than one meta description. | JSON object with `count` |
| `h1-missing` | `warning` | `medium` | An analysed Page has no `<h1>` or its first `<h1>` is empty. | SQL `NULL` |
| `h1-duplicate` | `opportunity` | `low` | An Indexable Page shares its non-empty first `<h1>` with another Indexable Page. The comparison is case-sensitive. | JSON object with `h1_1` and `pages`, the number of Pages in the group |
| `h1-multiple` | `warning` | `low` | A Page has more than one `<h1>`. | JSON object with `count` |
| `h1-too-long` | `opportunity` | `low` | A Page's first `<h1>` exceeds its recorded `max_chars` (default 70). | JSON object with `length` |
| `h2-missing` | `opportunity` | `low` | A Page has no `<h2>` or its first `<h2>` is empty. | SQL `NULL` |
| `canonical-missing` | `warning` | `medium` | An analysed Page has no canonical declaration and neither noindex directive. | SQL `NULL` |
| `canonicalised` | `warning` | `medium` | An analysed Page has the stored Indexability Status `canonicalised`. | JSON object with the absolute `canonical_url` |
| `canonical-to-non-indexable` | `issue` | `high` | An analysed Page declares a different URL as canonical and that target is Non-Indexable. | JSON object with `canonical_url` and `target_reason` |
| `canonical-conflicting` | `issue` | `high` | At least two canonical declarations disagree, leaving the preferred URL unresolved. | JSON object with `canonical_link_element_1`, `canonical_link_element_2` and `http_canonical`. A missing source is JSON `null`. |
| `canonical-relative` | `warning` | `low` | An analysed Page contains a relative canonical declaration. | SQL `NULL` |
| `noindex` | `warning` | `high` | An analysed Page has `pages.meta_robots_noindex = 1` or `pages.x_robots_tag_noindex = 1`. | JSON object with `sources`, the applicable directive sources |
| `nofollow` | `warning` | `medium` | An analysed Page has a nofollow directive in meta robots or `X-Robots-Tag`. | JSON object with `sources`, in the same order as for `noindex` |
| `meta-refresh` | `warning` | `low` | An analysed Page has an HTML meta refresh declaration. | JSON object with `meta_refresh` and the absolute `redirect_url`, or JSON `null` for the URL when no target was recorded |
| `low-word-count` | `opportunity` | `medium` | An analysed, Indexable Page has fewer than its recorded `min_words` words in its Content Area. The default is 200 words. | JSON object with the measured `word_count` |
| `exact-duplicate` | `issue` | `medium` | An analysed, Indexable Page shares its Content Area hash with another analysed, Indexable Page. | JSON object with `content_hash` and `pages`, the number of Pages sharing it |

The `internal_urls` population includes Internal URLs with `fetch_state` `fetched` or `error`,
or with `blocked_by_robots_txt = 1`, including URLs outside a Section Crawl's Scope. A
robots.txt timeout can record a fetch error for an Internal URL before the Crawl requests it.
When the Crawl receives a response but cannot record it, the `record_failed` warning reports
the write failure. The `internal-no-response` Rule excludes that case.

The Redirect Chain walk follows recorded targets, including External URLs. It counts each
recorded 3xx response once, including a terminal 3xx without a target, and stops at the first
non-3xx or unrequested URL, a 3xx without a target, or the first repeated URL.
`--max-redirects` limits how many consecutive redirects the Crawl follows. For example,
with `--max-redirects 1`, the Crawl can record two consecutive 301 responses and skip the
second response's target with `max_redirects`. The walk counts both responses (`hops = 2`)
and ends at the skipped target (`final_url`). It can also follow targets that the Crawl
requested separately. `redirect-chain` fires when `hops` exceeds the recorded Rule threshold
`max_hops`.
[Crawl hop limit](crawling.md#the-hop-limit)

The `redirect-loop` Rule requires a recorded `in_redirect_loop = 1` for each Affected URL,
even when the recorded targets form a closed loop.

The title, meta description and heading Rules apply to analysed Pages (`urls.parsed = 1`).
Missing measurements from a failed extractor do not trigger these Rules on their own.

In v0.1, `title-too-long` uses the title's recorded character count and returns `length`.
`meta-description-too-long` reads the first description's stored character count and pixel
width. A description can exceed the character limit when its width is unmeasured. Its
`width_px` detail is then JSON `null`. A value exactly at its limit passes that check.

For a short or missing title, name the Page's subject and what distinguishes it. For a long
title, put the distinguishing words first and shorten it to the configured limit. When a
template emits several titles, keep the one that describes the Page. For duplicate titles,
give each Indexable Page a distinct one. A title identical to the H1 can use extra context
that helps people recognise the Page in search results.

Read a Rule's guidance and reproducing SQL with [`linx rules show`](#read-one-rule).

The `canonicals`, `directives` and `content` categories apply to analysed Pages
(`internal_pages`, with `urls.parsed = 1`). `canonicalised` reads the stored Indexability
Status, so a self-canonical or a higher-priority status such as `noindex` gives no Issue
for that Rule. `canonical-missing` exempts Pages with a noindex directive from either source.

The canonical query matches the source Page's `pages.canonical_url` to the target's `urls.url`.
It reports the source Page as the Affected URL when that target is a different URL and is
Non-Indexable. For a target Page, the Rule reads the stored Indexability and uses its
Indexability Status as `target_reason`. The possible reasons are `blocked_by_robots_txt`,
`redirected`, `client_error`, `server_error`, `noindex` and `canonicalised`.

For a target without a Page, the Rule uses the first applicable reason in this order.

1. `blocked_by_robots_txt` applies when the Crawl records a robots.txt prohibition, including
   when the target was skipped and has zero requests.
2. `redirected` applies to a recorded 3xx response.
3. `client_error` applies to a recorded 4xx response or a status of 600 or above.
4. `server_error` applies to a recorded 5xx response.
5. `no_response` requires a failed request to the target URL itself (`fetch_state = 'error'`
   and `attempt_count > 0`). A robots.txt preflight failure leaves zero target attempts.
   The Rule excludes `fetch_error = 'record_failed'` from this reason because it describes a
   Store write failure, even with a positive attempt count.

An allowed 200 PDF gives no Issue. A skipped or queued target gives no Issue when the Crawl
has recorded neither a robots.txt prohibition nor a request outcome for it.

If the target `https://example.test/b` has the stored Indexability Status `redirected`,
the detail is `{"canonical_url": "https://example.test/b", "target_reason": "redirected"}`.
A target with the stored Indexability Status `noindex` gives
`{"canonical_url": "https://example.test/b", "target_reason": "noindex"}`.
A timeout requesting the target gives
`{"canonical_url": "https://example.test/b", "target_reason": "no_response"}`.
Run `linx rules show canonical-to-non-indexable` for the guidance and reproducing SQL.

For `noindex`, each source is listed when its stored flag is 1. If only the applicable
HTTP `X-Robots-Tag` header gives noindex, the detail is `{"sources": ["x_robots_tag"]}`.
When both sources apply, `meta_robots` comes first, as in
`{"sources": ["meta_robots", "x_robots_tag"]}`. The Rule uses the directive flags even when
the Page's Indexability Status is `blocked_by_robots_txt`.
Run `linx rules show noindex` for the guidance and reproducing SQL.
[Robots directives](crawling.md#robots-directives)

`nofollow` uses the Page-wide directive flags. `meta-refresh` reads the recorded HTML
declaration, including a timed reload with no target. The `redirect_url` is the Page's
recorded redirect target.

Both Content Rules require Indexable Pages. `low-word-count` counts words in the Content
Area and skips unmeasured counts. `exact-duplicate` excludes Pages without a hash. It
reports every member of a group of two or more Pages with the same hash.

### URLs

The `urls` Rules apply to analysed Pages (`internal_pages`). The character checks use the
display address's path and query. The encoded length uses the full requested URL.

| Rule id | Issue Type | Priority | Fires when | `detail` |
|---|---|---|---|---|
| `url-uppercase` | `opportunity` | `low` | The display path or query contains a Unicode uppercase letter (general category `Lu`), ignoring valid `%XX` escapes. | SQL `NULL` |
| `url-underscores` | `opportunity` | `low` | The display path contains an underscore. | SQL `NULL` |
| `url-parameters` | `opportunity` | `low` | The query string is non-empty. | SQL `NULL` |
| `url-too-long` | `opportunity` | `low` | The full encoded URL exceeds the recorded `max_chars` threshold (default 115 characters). | JSON object with `length` |
| `url-non-ascii` | `opportunity` | `low` | The display path or query contains a non-ASCII character. | SQL `NULL` |

For example, `/Кат/a%2F` contains an uppercase letter and a non-ASCII character.
`/a%2Fb` has no uppercase letter outside the escape. Uppercase and non-ASCII checks
ignore the host. The saved uppercase query uses the pinned Unicode 16.0 data and runs
in plain SQLite.

### Images

| Rule id | Issue Type | Priority | Applies to | Fires when | `detail` |
|---|---|---|---|---|---|
| `image-missing-alt-text` | `opportunity` | `low` | `internal_pages` | An analysed Page has an `<img src>` Link with a missing or empty `alt` attribute. | JSON object with `missing_alt_attribute` and `empty_alt`, counted separately |
| `image-too-large` | `opportunity` | `medium` | `resources` | An image target's recorded size exceeds `max_kb` × 1024 bytes (default 100 kilobytes), with HTML and XHTML responses excluded. | JSON object with `size_bytes` |
| `image-broken` | `issue` | `medium` | `resources` | The image target returns HTTP 400–599 or its request fails. | JSON object with `status_code` for an HTTP error or `error` for a failed request |

The alt Rule counts each measured `<img src>` occurrence on the Page once. It skips
`srcset` candidates, ordinary hyperlinks and Pages whose Link extraction failed. Keep
`alt=""` on intentionally decorative images.

Both target Rules use the outcome of a request to the target URL itself and an image Link from
a Page. They cover Internal and External targets regardless of how the Crawl found or requested
the URL. Each target appears once per Rule, even if several Pages reference it. If a hyperlink
led to `/bad` and returned an HTML 404, a later `<img src="/bad">` on another Page makes `/bad`
an Affected URL of `image-broken`. `image-too-large` excludes responses identified as
`text/html` or `application/xhtml+xml`. A robots.txt failure before any target attempt leaves
no result for either Rule. A `record_failed` warning reports a Store write error, which is
excluded from `image-broken`.

## Browse the catalogue

`linx rules` is shorthand for `linx rules list`. Use the full Command name before any options.

```sh
linx rules list --limit 1 --fields id,category
```

This example replaces the returned cursor with a placeholder.

```json
{
  "total": 42,
  "items": [{"id": "internal-4xx", "category": "response_codes"}],
  "next_cursor": "<opaque cursor>"
}
```

`total` counts all 42 Rules evaluated in v0.1. `items` contains the current page in
catalogue order, grouped by category. To see the next page in the same Workspace,
pass the returned `next_cursor` to `--cursor` and continue until it is `null`.
Treat the cursor as an opaque value.
`--format jsonl` prints one JSON object per item. `--format table` produces a table for people.
With either format, an available next page is reported as `more_items` on stderr.
[CLI paging and fields](cli.md#lists-paging-fields-and-cursors)

## Read one Rule

Pass a Rule's id to `linx rules show`. IDs are stable lowercase kebab-case names such as
`title-too-long`. Categories are lowercase snake_case enumeration values for grouping Rules,
such as `response_codes` or `titles`.

```sh
linx rules show title-too-long
```

The Command returns one JSON object, shown here with indentation. `linx rules list` returns
the same fields in each item by default.

```json
{
  "id": "title-too-long",
  "category": "titles",
  "issue_type": "opportunity",
  "priority": "medium",
  "applies_to": "internal_pages",
  "enabled": true,
  "thresholds": {"max_chars": {"value": 60, "default": 60, "unit": "characters"}},
  "description": "A Page's first title is longer than max_chars characters.",
  "why_it_matters": "Search engines cut a long title short in their results, so its end, often the brand or what sets the Page apart, is not shown.",
  "how_to_fix": "Shorten the title to the limit, with the words that describe the Page first.",
  "reproduce_sql": "SELECT pages.url_id, json_object('length', pages.title_1_length) AS detail\nFROM pages\nJOIN urls ON urls.id = pages.url_id\nWHERE urls.parsed = 1 AND pages.title_1_length > (\n    SELECT json_extract(thresholds, '$.max_chars') FROM rules WHERE id = 'title-too-long'\n)"
}
```

The query reads the effective character limit recorded in the Crawl. The `length`
in each Affected URL's detail is the measured length of the first title.

`applies_to` names the Rule's intended population, such as `internal_pages` for title Rules or
`internal_urls` for response-code Rules. The model also allows `resources` for Rules about
image Resources.

`enabled` is `true` by default. Set `enabled = false` in the Rule's table in the Workspace
settings to turn it off. Both Commands still show the Rule, with `"enabled": false`.

For example, to disable `title-missing`, add this table to the Workspace's `openlinx.toml`.

```toml
[rules.title-missing]
enabled = false
```

`thresholds` maps each threshold name to its integer `value`, catalogue `default` and `unit`.
Here `max_chars` is 60 characters, the default when the Workspace has no override. A Rule without
thresholds, such as `title-missing`, returns `{}`. `description`, `why_it_matters` and
`how_to_fix` carry the Rule's guidance.

Use `--format table` after the id to read the result as a table. An unknown id returns exit
code 4 with `rule_not_found` on stderr and a hint to run `linx rules list`.
[CLI diagnostics](cli.md#diagnostics)

## Override a threshold

In the Workspace's `openlinx.toml`, name the Rule by its id and set its threshold to a
non-negative integer of at most 4300 decimal digits. The limit applies to the numeric value,
regardless of TOML notation or digit separators. A larger value raises `settings_invalid`
(exit code 3) when a Command reads the Workspace, with the settings file and full threshold key.

```toml
[rules.title-too-long]
max_chars = 70
```

Both Commands show `{"value": 70, "default": 60, "unit": "characters"}` for `max_chars`.

Use [Workspace discovery](workspace.md#finding-the-workspace) or select a Workspace explicitly.

```sh
linx rules show title-too-long --workspace ./site
```

## Diagnose a misspelt Rule id

If the threshold example uses `[rules.title-to-long]` in `openlinx.toml`, running
`linx rules list` exits with code 3. The `settings_invalid` diagnostic on stderr identifies
`rules.title-to-long` in `details.errors[0].key`. Its hint reads
`Did you mean rules.title-too-long?` Rename the table to `[rules.title-too-long]`.

## Settings and Crawls from preview versions

The preview Workspace template included tables for `h2-missing`, `low-word-count` and
`url-parameters`. New Crawls accept valid settings in those tables. An empty table uses the
catalogue defaults. For example, `min_words = 300` in `[rules.low-word-count]` sets the
word-count threshold to 300 for the next Crawl.

Continuing a Crawl keeps its recorded Rules and thresholds. If a preview Crawl recorded one
of those three Rules with the preview query that returned zero rows, it continues to report
zero Affected URLs for that Rule. Start a new Crawl to evaluate all 42 Rules. The recorded
`title-too-long.max_chars` threshold still controls which titles appear in an older Crawl.

## Read Issues from a crawl file

Run these queries against the SQLite file of a Crawl with `title-missing` enabled.
The current catalogue also includes `h1-missing`. Its Issues appear separately when Pages
lack an H1. These examples filter to `title-missing`.

The [`rules` table](schema.md#table-rules) holds the catalogue, effective settings and
reproducing SQL recorded when the Crawl was created.

```sql
SELECT id, enabled, thresholds, reproduce_sql
FROM rules
WHERE id = 'title-missing';
```

The [`affected_urls` table](schema.md#table-affected_urls) holds the last pass's rows. Join
on `url_id` to see each URL. The `title-missing` Rule checks `pages.title_count` and
`pages.title_1` and returns SQL NULL for `detail`.

```sql
SELECT urls.url, affected_urls.detail
FROM affected_urls
JOIN urls ON urls.id = affected_urls.url_id
WHERE affected_urls.rule_id = 'title-missing'
ORDER BY urls.url;
```

The [`issues` view](schema.md#view-issues) counts those rows per Rule. A Rule with no
Affected URLs has no row in the view.

```sql
SELECT rule_id, issue_type, priority, affected_count
FROM issues
WHERE rule_id = 'title-missing';
```

For a `completed` or `stopped` Crawl, the Issues reader reads the final pass from
`affected_urls` and `issues`. For a `running`, `failed` or `interrupted` Crawl, the reader
computes live results over the available data using queries from the installed Rule catalogue.
It uses the Crawl's `rules` snapshot to determine which Rules are enabled. Queries that use
thresholds read them from that same snapshot. Direct reads of `affected_urls` and `issues`
show stored rows. A resumed Crawl can still have rows from its previous pass.

## Reproducing queries

Both Rules Commands include `reproduce_sql`, a read-only SELECT that returns `url_id`
and `detail` from a crawl file. Run this example from the Crawl's Workspace and replace
`<crawl-id>` with its id. `jq` decodes the SQL from the Command's JSON output for the
SQLite CLI.

```sh
crawl_file='.openlinx/crawls/<crawl-id>.sqlite'
query=$(linx rules show title-missing | jq -er '.reproduce_sql') &&
  sqlite3 -readonly -header -column "$crawl_file" "$query"
```

To compare this query with the definition recorded at Crawl creation, inspect
`rules.reproduce_sql` in the crawl file. The recorded `enabled` value shows whether
the Rule was enabled for that Crawl.
