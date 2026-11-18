# Rules

A Rule defines a deterministic condition on Crawl data and provides fixed guidance on what it
means, why it matters and how to fix it. When a Rule fires in a Crawl, it produces an Issue with
the URLs it affects. Each of those URLs is an Affected URL. [Glossary](../CONTEXT.md#analysis)

`linx rules list` and `linx rules show` currently describe the built-in catalogue. They work
without a Workspace or Crawl and show catalogue defaults. Reading the catalogue does not run
the Rules or tell you which URLs are affected.

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

## Browse the catalogue

`linx rules` is shorthand for `linx rules list`. Use the full Command name before any options.

```sh
linx rules list --limit 1 --fields id,category
```

```json
{
  "total": 4,
  "items": [{"id": "internal-4xx", "category": "response_codes"}],
  "next_cursor": "eyJ2IjoxLCJxIjoiNTAzZmFkY2E1NzU2NzNkOSIsImsiOjF9"
}
```

`total` counts the entire catalogue. `items` contains the current page in catalogue order,
grouped by category. To see the next page, pass the returned `next_cursor` to `--cursor` and
continue until it is `null`. Treat the cursor as an opaque value. `--format jsonl` prints one
JSON object per item. `--format table` produces a table for people. With either format, an
available next page is reported as `more_items` on stderr.
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
  "thresholds": {"max_chars": {"value": 60, "default": 60, "unit": "characters"}},
  "description": "A Page's first title is longer than max_chars characters.",
  "why_it_matters": "Search engines cut a long title short in their results, so its end, often the brand or what sets the page apart, is not shown.",
  "how_to_fix": "Shorten the title to the limit, with the words that describe the page first."
}
```

`applies_to` names the Rule's intended population, such as `internal_pages` for title Rules or
`internal_urls` for response-code Rules. The model also allows `resources` for Rules about
image Resources.

`thresholds` maps each threshold name to its integer `value`, catalogue `default` and `unit`.
Here `max_chars` is 60 characters. `value` currently equals `default`. A Rule without
thresholds, such as `title-missing`, returns `{}`. `description`, `why_it_matters` and
`how_to_fix` carry the Rule's guidance.

Use `--format table` after the id to read the result as a table. An unknown id returns exit
code 4 with `rule_not_found` on stderr and a hint to run `linx rules list`.
[CLI diagnostics](cli.md#diagnostics)

## Planned evaluation and configuration

The planned evaluation uses a SQL query per Rule over stored Crawl data. The query identifies
Affected URLs. Workspace Rule overrides, the recorded Rule configuration, Issue evaluation and
the Health Score are planned separately from the catalogue Commands described above. The
catalogue output will expose effective settings and the reproducing query when those features
are implemented. [Planned v0.1 catalogue](../ROADMAP.md#the-v01-rules)
