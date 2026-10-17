# Rules

How a Crawl's data becomes Issues: the Rules, what their Issue Type and Priority mean, and how to read `spider rules`. The spec is [openspec/changes/040-add-rules/specs/rules/spec.md](../openspec/changes/040-add-rules/specs/rules/spec.md), and terms follow [CONTEXT.md](../CONTEXT.md).

## The Rule model

A Rule is a deterministic check with fixed guidance. Every Rule has:
- `id`: kebab-case, such as `title-too-long`. It is never renamed or reused, so a script or a `spider.toml` that names it keeps working.
- `category`: one of `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images`, in this order.
- `issue_type` and `priority`: see below.
- `applies_to`: the population the Rule checks. `internal_urls` are the Internal URLs that were requested; `internal_pages` are the analysed Pages ([page-data.md](page-data.md#analysed-and-non-analysed-pages)); `resources` are the Resources that Pages reference, in v0.2 the images. A Rule's query joins the view of its population ([schema.md](schema.md)): `internal_urls`, `analysed_pages`, or `indexable_pages` for the Rules that compare Indexable Pages.
- `thresholds`: the named limits of the Rule, each a non-negative integer with a default and a unit (`characters`, `pixels`, `words`, `kilobytes` or `hops`). A Rule without limits has none.
- `description`, `why_it_matters` and `how_to_fix`: fixed English guidance, the same in every Crawl, so an agent can explain an Issue without judgement calls.
- `reproduce_sql`: the Rule's reproducing query, the only form of its condition (see [Checking an Issue with its query](#checking-an-issue-with-its-query)).

v0.1 ships 15 Rules. The other 27 of the catalogue come in v0.2.

## Issue Type and Priority

The Issue Type says how certain the problem is:
- `issue`: a definite defect, such as a page that answers 404. Issue-type Issues alone lower the Health Score.
- `warning`: something to check, which can be intended, such as a redirect, a noindex Page or a URL that robots.txt blocks.
- `opportunity`: something that could be better, such as a title that search engines cut short.

The Priority says how urgently to fix it: `high`, `medium` or `low`.

`issue` is kept for definite defects because it decides the Health Score: anything that can be intended is a `warning`. `http-url`, a Page served over plain HTTP, is a Warning with High Priority: it comes first among the Warnings, while the Health Score still reflects the site's other defects.

## Names

Categories are snake_case, such as `meta_descriptions`, because they are stored values of an enumeration, and every stored enumeration value is snake_case. Rule ids are kebab-case, such as `meta-description-missing`, because people type them as command arguments and as `spider.toml` table names, where `-` is allowed.

## The catalogue

Each Rule fires for a URL of its population when the condition holds, and records the measured values named under `detail` as a JSON object, or NULL when it names none. A Rule never fires on a value that was not measured (NULL).

| id | Category | Issue Type | Priority | Fires for… | `detail` |
|---|---|---|---|---|---|
| `internal-4xx` | `response_codes` | `issue` | `high` | an Internal URL with a `status_code` from 400 to 499 | `status_code` |
| `internal-5xx` | `response_codes` | `issue` | `high` | an Internal URL with a `status_code` from 500 to 599 | `status_code` |
| `internal-no-response` | `response_codes` | `issue` | `high` | an Internal URL with `fetch_state` `error` and any `fetch_error` other than `record_failed` | `error`: the URL's `fetch_error` |
| `title-missing` | `titles` | `issue` | `high` | an analysed Page whose `title_count` is 0 or whose `title_1` is the empty string | none |
| `title-duplicate` | `titles` | `warning` | `medium` | an Indexable Page whose non-empty `title_1` is, letter case included, the `title_1` of another Indexable Page | `title_1`, and `pages`: how many Indexable Pages have it |
| `title-too-long` | `titles` | `opportunity` | `medium` | an analysed Page whose `title_1_length` is above `max_chars`, 60 characters by default | `length`: the `title_1_length` |
| `h1-missing` | `headings` | `warning` | `medium` | an analysed Page whose `h1_count` is 0 or whose `h1_1` is the empty string | none |

`record_failed` means that the Crawl received a response but could not record it. That is the tool's failure, not the site's, so it is no Issue: the `record_failed` warning reports it, and continuing the Crawl requests the URL again. The query of `internal-no-response` says so in an SQL comment.

`title-too-long` counts characters only in v0.1; pixel widths come in v0.2. `title-duplicate` compares every analysed Page until the crawl store records Indexability.

`spider rules show <id>` prints each Rule's guidance: what it checks, why it matters and how to fix it.

## Reading `spider rules`

`spider rules list` lists the Rules in catalogue order: by category, in the order of the Rule model, then in the order of the spec's tables. It is a list Command ([cli.md](cli.md#lists-paging-fields-and-cursors)), so it takes `--limit` (50 by default), `--cursor`, `--fields` and `--format`, and `--workspace` for a Workspace other than the nearest one. `spider rules` with no arguments runs `spider rules list`; options go after `list`. Each item has `id`, `category`, `issue_type`, `priority`, `applies_to`, `enabled`, `thresholds`, `description`, `why_it_matters`, `how_to_fix` and `reproduce_sql`:

```
spider rules list --limit 1
{"total":…,"items":[{"id":"internal-4xx","category":"response_codes","issue_type":"issue","priority":"high","applies_to":"internal_urls","enabled":true,"thresholds":{},"description":"An Internal URL responded with a client error, a status code from 400 to 499.","why_it_matters":"…","how_to_fix":"…","reproduce_sql":"…"}],"next_cursor":"…"}
```

`spider rules show <id>` prints one Rule as a document with the same fields. `enabled` is false for a Rule that the Workspace turns off, and `thresholds` maps each limit's name to its `value` in the Workspace, its `default` and its `unit`:

```
spider rules show title-too-long
{"id":"title-too-long","category":"titles","issue_type":"opportunity","priority":"medium","applies_to":"internal_pages","enabled":true,"thresholds":{"max_chars":{"value":60,"default":60,"unit":"characters"}},…}
```

An id that no Rule has fails with `rule_not_found` (exit code 4), whose hint points to `spider rules list` and whose `details.suggestions` lists the closest Rule ids.

## Settings: `[rules.<id>]`

A table named by a Rule's id in the Workspace's `spider.toml` changes that Rule in the Workspace, as `spider rules` shows it.

Raise a limit, here the title length, from 60 to 70 characters:

```toml
[rules.title-too-long]
max_chars = 70
```

Turn a Rule off, which `spider rules` shows as `enabled` false:

```toml
[rules.h1-missing]
enabled = false
```

A table may hold `enabled`, a boolean, and the Rule's thresholds by name, each an integer from 0 to 2^63-1, SQLite's largest INTEGER; `spider rules show <id>` lists a Rule's thresholds. Anything else stops every Command that reads the settings with `settings_invalid` (exit code 3), before a Crawl requests any URL. `details.errors[].key` is the dotted key, and the hint names the closest Rule id or key when there is one:

```
spider rules list
{"level":"error","code":"settings_invalid","message":"The settings file …/spider.toml is invalid.","hint":"Did you mean rules.title-too-long?","details":{"file":"…/spider.toml","errors":[{"key":"rules.title-to-long","message":"Extra inputs are not permitted"}]}}
```

## Issues in a crawl file

A Crawl records the configuration of its Rules when it is created, and its Issues when it ends, in its crawl file ([schema.md](schema.md)). Editing `spider.toml` later changes neither.

`rules` has one row for each Rule, as the Crawl uses it: its metadata, `enabled`, the `thresholds` it uses as a JSON object of names to integers, its guidance and `reproduce_sql`. The title limit a Crawl used:

```sql
SELECT json_extract(thresholds, '$.max_chars') FROM rules WHERE id = 'title-too-long';
```

`affected_urls` has one row for each Rule and Affected URL, with `detail`, the measured values as a JSON object, or NULL for a Rule that measures none. The Pages without a title:

```sql
SELECT urls.url
FROM affected_urls JOIN urls ON urls.id = affected_urls.url_id
WHERE affected_urls.rule_id = 'title-missing';
```

`issues` is a view with one row for each Rule that has at least one Affected URL: `rule_id`, `category`, `issue_type`, `priority`, and `affected_count`, counted from `affected_urls`. The Issue-type Issues, largest first:

```sql
SELECT rule_id, priority, affected_count FROM issues
WHERE issue_type = 'issue' ORDER BY affected_count DESC;
```

### Checking an Issue with its query

Every Rule is one read-only `SELECT` over the crawl file that returns its Affected URLs as `url_id` and `detail`. `rules.reproduce_sql` holds it, and `spider rules list` and `show` print it. A query reads its thresholds from the Crawl's own `rules` row, so it gives that Crawl's answer with the thresholds the Crawl was created with. To check an Issue of your own crawl file, run the query over it through a read-only connection, here with the SQLite shell:

```
sqlite3 -readonly .spider/crawls/20260927-140312-k3f9.sqlite "SELECT reproduce_sql FROM rules WHERE id = 'title-missing'"
SELECT url_id, NULL AS detail
FROM pages
WHERE title_count = 0 OR title_1 = ''
```

Then run the printed query the same way. A query that leaves out a value its condition would otherwise match says why in an SQL comment. A crawl file someone else gave you is data, and its `reproduce_sql` may hold any SQL: take the query from `spider rules show <id>` instead, which prints the tool's own. The tool itself runs the queries of its own Rules, never the text a crawl file holds.

### Live and stored Issues

- **While a Crawl runs,** it stores no Issue: `affected_urls` is empty, or holds an earlier pass's rows when the Crawl was resumed, and the Issues are computed on each read from the queries of the Rules that the Crawl's `rules` table marks enabled. A running Crawl therefore shows its Issues so far, at the cost of running every query on each read.
- **When a Crawl ends as `completed` or `stopped`,** its post-crawl pass stores them, before the Crawl State is written: `affected_urls` and `issues` then hold that pass's result, and they are read as stored. A resumed Crawl's pass replaces them.
- **A Crawl that `failed`, or whose process died,** got no final pass, and its `affected_urls` may still hold an earlier pass's rows. Its Issues are computed as for a running Crawl, so trust `affected_urls` and `issues` only when `crawl.state` is `completed` or `stopped`.
