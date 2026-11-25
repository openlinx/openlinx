# Querying Issues

Use `linx issues` to find which Rules found Affected URLs in a Crawl. Pass a
`rule_id` from the list to `linx issue` to see the recorded Rule and its
Affected URLs. Both Commands open the crawl file read-only and read one
consistent snapshot per invocation.

## Listing Issues

`linx issues` takes no positional arguments. It returns one item per Rule
with at least one Affected URL. Each item contains `rule_id`, `category`,
`issue_type`, `priority`, `affected_count` and `description`. The count is
the number of Affected URLs for that Rule, and the description comes from the
Rule recorded for the Crawl. The JSON `total` counts matching Issues before
paging.

Items are ordered by Issue Type (`issue`, `warning`, `opportunity`), then
Priority (`high`, `medium`, `low`), then decreasing `affected_count`, then
ascending `rule_id`.

| Flag | Selects |
|---|---|
| `--type` | Issue Types `issue`, `warning` or `opportunity`. |
| `--priority` | Priorities `high`, `medium` or `low`. |
| `--category` | Rule category IDs. See the `category` column in `linx schema rules` for the accepted values. |

Each flag accepts comma-separated and repeated values, ignoring case. An
Issue must match any value within a flag and every flag supplied. An unknown
value returns `invalid_value` with the accepted values in `details.accepted`.

```sh
linx issues --type issue,warning --priority high
linx issues --category headings
```

## Viewing an Issue

`linx issue <rule-id>` takes one recorded Rule ID. Its JSON response contains
`rule`, `total`, `items` and `next_cursor`. The `rule` header includes the
recorded `rule_id`, `category`, `issue_type`, `priority`, `description`,
`why_it_matters`, `how_to_fix`, `thresholds` and `reproduce_sql`.
`thresholds` gives the values used for that Crawl. `reproduce_sql` is the
recorded read-only SELECT to run against the same SQLite crawl file. Its
result columns are `url_id` and `detail`.

`total` counts the Rule's Affected URLs before paging. Items appear in
ascending `url` order and contain `url` and `detail` by default. `detail`
holds the Rule's measured values for that URL, or `null` when it supplies
none. For an Internal URL returning HTTP 404, `internal-4xx` gives
`{"status_code": 404}` in `detail`.

```sh
linx issue internal-4xx
linx issue internal-4xx --fields url --format jsonl
```

When a recorded Rule has no Affected URLs, the JSON response still includes
the Rule, with `"total": 0` and `"items": []`. An unknown Rule ID returns
`rule_not_found` with suggestions from the Crawl's recorded Rule IDs. Passing
a Rule ID to `linx issues` returns `usage_error` with a hint for the detail
Command.

## Flags shared by both Commands

| Flag | Use |
|---|---|
| `--workspace <path>` | Select the Workspace. Without the flag, use the nearest Workspace found upward from the current folder, then the global Workspace. See [Workspace discovery](workspace.md#finding-the-workspace). |
| `--crawl <selection>` | Select `latest` (the Crawl that started last and the default), a Crawl ID or a crawl-file path. See [Selecting a Crawl](crawl-store.md#selecting-a-crawl). |
| `--format <format>` | Choose `json` (default), `jsonl` or `table`. JSON includes the paging envelope and, for `linx issue`, the Rule header. JSONL and table print the items. |
| `--limit <n>` | Set the maximum number of items in the page, from 0 to 1000 (default 50). In JSON, 0 keeps `total`, with an empty `items` list and a null `next_cursor`. |
| `--cursor <value>` | Pass the previous page's `next_cursor` to continue. |
| `--fields <names>` | Select comma-separated item fields, or pass `all`. The fields listed for each Command above are also its defaults. This flag preserves the JSON Rule header. |
| `--help` | Print the Command's usage and options. |

A cursor belongs to the Command and the resolved Crawl ID. For `issues`, it
also belongs to the filter values after splitting, case normalisation and
deduplication, independent of their order. For `issue`, it belongs to the
Rule ID. A different binding returns `invalid_cursor`. If `latest` resolves
to a new Crawl, select the original Crawl or start again without a cursor.
See [paging and fields](cli.md#lists-paging-fields-and-cursors) for how to
continue from JSONL or table output.

## When Issues are computed

For a `completed` or `stopped` Crawl, both Commands read the results stored by
the post-crawl passes. For a `running`, `failed` or `interrupted` Crawl, Issues
are computed live on every call from the rows stored so far, using the Rules
enabled for that Crawl and their recorded thresholds. On a running Crawl the
counts and Affected URLs can change between requests, including between pages
of the same query.
