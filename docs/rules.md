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
| `warning` | Something to check. It can be intentional or the design can exclude it from the Health Score. |
| `opportunity` | Something that could be improved, such as a long Page title. |

Priority is the urgency of the fix, expressed as `high`, `medium` or `low`. In the planned
Health Score, an Internal Page counts against the score only if it is an Affected URL of at
least one Rule of type `issue`. Priority carries no weight in the calculation.

The planned `http-url` Rule is a Warning with High Priority. It flags Internal URLs that serve
successful responses over plain HTTP so maintainers can prioritise moving them to HTTPS. A
redirect from HTTP to HTTPS does not trigger this Rule. The Warning leaves the Health Score
unchanged.

## Rules evaluated by a Crawl

| Rule id | Issue Type | Priority | Fires when | `detail` |
|---|---|---|---|---|
| `internal-4xx` | `issue` | `high` | An Internal URL has a recorded HTTP status from 400 through 499. | JSON object with `status_code` |
| `internal-5xx` | `issue` | `high` | An Internal URL has a recorded HTTP status from 500 through 599. | JSON object with `status_code` |
| `internal-no-response` | `issue` | `high` | An Internal URL has `fetch_state = 'error'` and a recorded `fetch_error` other than `record_failed`. | JSON object with `error`, the recorded `fetch_error` |
| `title-missing` | `issue` | `high` | An analysed Page has no `<title>` or its first `<title>` is empty. | SQL `NULL` |
| `title-duplicate` | `warning` | `medium` | An analysed, Indexable Page shares its non-empty first title with another analysed, Indexable Page. The comparison is case-sensitive. | JSON object with `title_1` and `pages`, the number of Pages sharing the title |
| `title-too-long` | `opportunity` | `medium` | An analysed Page's first title exceeds its recorded `max_chars` limit (default 60). | JSON object with `length`, the measured character count |
| `h1-missing` | `warning` | `medium` | An analysed Page has no `<h1>` or its first `<h1>` is empty. | SQL `NULL` |

The response-code Rules use the recorded outcome for each Internal URL, including those
outside a Section Crawl's Scope and URLs without a Page. A robots.txt timeout can record
a fetch error for an Internal URL before the Crawl requests that URL. When the
Crawl receives a response but cannot record it, the `record_failed` warning reports the
write failure. The `internal-no-response` Rule excludes that case.

The title and heading Rules apply to analysed Pages (`urls.parsed = 1`). Missing measurements
from a failed extractor do not trigger these Rules on their own. Read a Rule's guidance
and reproducing SQL with [`linx rules show`](#read-one-rule).

## Browse the catalogue

`linx rules` is shorthand for `linx rules list`. Use the full Command name before any options.

```sh
linx rules list --limit 1 --fields id,category
```

This example replaces the returned cursor with a placeholder.

```json
{
  "total": 10,
  "items": [{"id": "internal-4xx", "category": "response_codes"}],
  "next_cursor": "<opaque cursor>"
}
```

`total` counts the entire catalogue. `items` contains the current page in catalogue order,
grouped by category. To see the next page in the same Workspace, pass the returned `next_cursor`
to `--cursor` and continue until it is `null`. Treat the cursor as an opaque value.
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

For example, to disable `url-parameters`, add this table to the Workspace's `openlinx.toml`.

```toml
[rules.url-parameters]
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
For `low-word-count`, set `min_words` under `[rules.low-word-count]`. The catalogue default
is 200 words.

Use [Workspace discovery](workspace.md#finding-the-workspace) or select a Workspace explicitly.

```sh
linx rules show title-too-long --workspace ./site
```

## Diagnose a misspelt Rule id

If the threshold example uses `[rules.title-to-long]` in `openlinx.toml`, running
`linx rules list` exits with code 3. The `settings_invalid` diagnostic on stderr identifies
`rules.title-to-long` in `details.errors[0].key`. Its hint reads
`Did you mean rules.title-too-long?` Rename the table to `[rules.title-too-long]`.

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
