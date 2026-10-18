# Querying a Crawl

How to read a Crawl's Issues with `spider issues`, and one Issue with `spider issue <rule-id>`; it also describes the where language, which filters rows by their columns. The spec is [openspec/changes/050-add-query-and-segments/specs/querying/spec.md](../openspec/changes/050-add-query-and-segments/specs/querying/spec.md), and terms follow [CONTEXT.md](../CONTEXT.md). The Rules behind the Issues are described in [rules.md](rules.md).

Every query Command reads the Crawl that `--crawl` selects: `latest` (the default, the Crawl that started last), a crawl id, or the path of a crawl file. It never changes the crawl file. In WAL mode, the default, each run reads one snapshot of it, so its numbers agree with each other even while the Crawl is still writing. A crawl file in rollback-journal mode, such as one on a network share, is read statement by statement instead, so a run during a Crawl may see rows that one of its statements missed.

## Live and stored Issues

Which Issues a Command shows depends on the Crawl State:
- **`completed` or `stopped`:** the Issues that the Crawl's post-crawl pass stored, in the `issues` view and the `affected_urls` table. They match what an agent reads there with SQL.
- **`running`, `failed` or `interrupted`:** the Issues are computed live on every call, by running each enabled Rule's query over the rows stored so far. `affected_urls` is not read then: after a resume it still holds the previous pass's rows. A live read of a large Crawl takes longer than a stored one.

A Crawl explains its Issues with its own `rules` table, the Rules and settings it was created with, so a crawl file made by another version of the tool keeps its texts and thresholds. On a Crawl that is computed live, a Rule that the file records but this version does not know cannot be computed: its query is in the file's `rules` table, and you can run it yourself with `spider sql`.

## `spider issues`

Lists the Issues of a Crawl, one item per Rule with at least one Affected URL:

```
spider issues
spider issues --type issue --priority high
spider issues --category titles,headings --crawl 20260927-140312-k3f9
```

Each item is:

| Field | Meaning |
|---|---|
| `rule_id` | The Rule that fired, such as `title-missing`. |
| `category` | The Rule's category, such as `titles`. |
| `issue_type` | `issue`, `warning` or `opportunity`. |
| `priority` | `high`, `medium` or `low`. |
| `affected_count` | The number of the Issue's Affected URLs. |
| `description` | The Rule's description, as the Crawl's `rules` table records it. |

**Order:** by Issue Type (`issue`, then `warning`, then `opportunity`), then by Priority (`high`, `medium`, `low`), then by `affected_count`, largest first, then by `rule_id`.

**Filters:**
- `--type`, `--priority` and `--category` take comma-separated values, and each can be repeated: `--type issue,warning` is the same as `--type issue --type warning`. Values are case-insensitive.
- The values of one flag are alternatives, and different flags must all match: `--type issue,warning --priority high` lists the Issues of Issue Type `issue` or `warning` with high Priority.
- An unknown value fails with `invalid_value` (exit code 2), which names the first unknown value given and whose `details.accepted` lists every accepted value of the flag, in order. An empty value, as in `--type issue,,warning`, fails the same way.
- `--category` accepts the categories of this version of the tool, so a category that only a later version's Rule has cannot be filtered on.

**Global flags:** `--crawl`, `--workspace` and `--format` (`json`, `jsonl` or `table`) work as in every Command ([cli.md](cli.md)).

**Paging:** the list is paged as every list Command is ([cli.md](cli.md#lists-paging-fields-and-cursors)), with `--limit`, `--cursor` and `--fields`. A cursor is bound to the Crawl it was read from, by its id, and to the filters: reused after a new Crawl started, or with other filters, it fails with `invalid_cursor`. A Crawl holds at most one item per Rule, so the default `--limit` of 50 shows them all.

## The Affected URLs of one Issue: `spider issue <rule-id>`

`spider issue <rule-id>` returns the Rule and a page of its Affected URLs; `spider issues` takes no Rule id:

```
spider issue title-missing
spider issue internal-4xx --fields url --limit 100
```

Its output:

```json
{"rule": {...}, "total": 1, "items": [{"url": "https://example.com/gone", "detail": {"status_code": 404}}], "next_cursor": null}
```

- `rule` is the Rule as the Crawl's `rules` table records it: `rule_id`, `category`, `issue_type`, `priority`, `description`, `why_it_matters`, `how_to_fix`, `thresholds` and `reproduce_sql`. `thresholds` maps each threshold name to the value that applied to this Crawl. `reproduce_sql` is the Rule's query: run it with `spider sql` to read the Affected URLs as they are now.
- Each item is `{url, detail}`, the fields `--fields` chooses from. `url` is the URL as the `urls` table records it, the form that `spider sql` returns. `detail` is the JSON object of the values the Rule measured for that URL, or `null` for a Rule that measures none.
- `total` counts every Affected URL. A Rule that did not fire has `total` 0 and no items.
- **Order and paging:** the Affected URLs come in `url` order, paged by keyset with `--limit` and `--cursor`: each page starts after the last URL of the one before, so the pages of a stored Issue never repeat or skip a URL. On an Issue computed live, an Affected URL that appears between two pages and sorts before the cursor is not shown, and `total` can change from page to page. A cursor is bound to the Crawl and the Rule.
- **Unknown rule id:** it fails with `rule_not_found` (exit code 4), whose hint points to `spider rules list` and whose `details.suggestions` lists the closest Rule ids of the Crawl's `rules` table.

## The where language

A `--where` expression picks rows by their columns. It is parsed before any query runs, and it never reaches SQLite as text: every value is bound as a parameter.

```
status_code >= 400
status_code = 404 and crawl_depth > 3
crawl_depth <= 2 and status_code <> 200
title_1 contains 'каталог'
meta_description_1 is not null
```

| Form | A row matches when |
|---|---|
| `column = value`, `column != value` (or `<>`) | the column equals the value, or does not. Text compares exactly, case included. |
| `column < value`, `<=`, `>`, `>=` | numbers compare numerically, text by Unicode code point. |
| `column contains 'text'` | the column's text holds `text`, ignoring case in any script: `title_1 contains 'КАТАЛОГ'` matches `Каталог товаров`. A number column is read as its text, so `status_code contains '0'` matches 404. |
| `column is null`, `column is not null` | the column has no value, or has one. |
| `expression and expression` | both match. |

- **Values:** a number (`404`, `-1.5`), a string in single or double quotes, or `true` and `false` for a boolean column. A string writes its own quote twice: `'It''s here'` is the same as `"It's here"`. Backslashes are ordinary characters.
- **Names:** column names and the keywords `and`, `contains`, `is`, `not`, `null`, `true` and `false` are case-insensitive.
- **Null values:** every form except `is null` and `is not null` is false where the column is null. `word_count < 300` and `word_count != 250` both leave out a row without a word count; `word_count is null` finds it.
- **Not in this version:** `or`, `not`, parentheses, the regular-expression operators `~` and `!~`, `in` and `not contains` are syntax errors.

**On the command line,** put the whole expression in double quotes and its strings in single quotes. This works in PowerShell, cmd and POSIX shells alike:

```
--where "title_1 contains 'blog' and status_code = 200"
```

Inside the double quotes, PowerShell and POSIX shells still expand `$` and read the backtick, and cmd expands `%NAME%`.

**Errors:** an expression that breaks this grammar fails with `invalid_where` (exit code 2) before any query runs, with a message that names the token it could not read, or what it expected there, and a hint that recalls the grammar.

## What a query costs

On a Crawl of about 500,000 URLs, what an index serves decides whether a call takes milliseconds or seconds:
- **`spider issues`:** a stored list is one scan of `affected_urls`' primary key, grouped by Rule. A live list runs every enabled Rule's query.
- **`spider issue <rule-id>`:** a stored Issue reads the Rule's rows of `affected_urls` by their key prefix, joins them to `urls` by key and sorts them by `url` for each page, so its cost grows with the Issue, not with the Crawl. A live Issue runs the Rule's query on every call.
