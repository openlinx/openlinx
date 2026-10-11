# The CLI contract

How every `spider` Command talks to agents and people. The spec is [openspec/specs/cli-contract/spec.md](../openspec/specs/cli-contract/spec.md). Terms follow [CONTEXT.md](../CONTEXT.md).

`spider commands` describes every Command, the exit codes and the diagnostic codes as one JSON document. Agents read it instead of this page.

## stdout and stderr

| Stream | Carries |
|---|---|
| stdout | the Command's result only: one compact JSON document followed by `\n`, or JSON Lines (see [Formats](#formats)) |
| stderr | JSON lines only: diagnostics, and progress events from Commands that report progress |

- **UTF-8 bytes and `\n`** on every OS, whatever the console code page or `PYTHONIOENCODING`. Non-ASCII characters are written as themselves, never as `\u` escapes.
- **Nothing on stdout when a document or list Command fails.** Its result is written only when the Command ends, so a failure leaves stdout empty. A rows Command is the exception by design: each row is written as it is made, so the rows before a failure stay on stdout and the error follows on stderr. So is a Command whose result describes the failed outcome: it prints that result, then the error.
- **Plain text** appears in three places only, all on stdout with exit code 0:
  - `--help`, on the tool or on any Command
  - `spider` with no arguments, which prints the same as `spider --help`
  - `spider --version`, which prints `spider <version>`
- **`--format`** chooses the format of the result. Each Command supports the formats that `spider commands` lists for it. Any other format fails with `invalid_value`, and the hint lists the Command's formats. Errors stay JSON whatever `--format` says.

```
spider commands --format jsonl
```

stdout stays empty, the exit code is 2, and stderr has:

```json
{"level":"error","code":"invalid_value","message":"This Command has no jsonl format.","hint":"Use --format with one of: json, table.","details":{}}
```

An unknown format, such as `--format xml`, is `invalid_value` too.

## Formats

Every Command has an output kind, and the kind decides the formats the Command can offer:

| Output kind | Result | Formats (default first) |
|---|---|---|
| `document` | one JSON object | `json`, `table` |
| `list` | the paging envelope `{total, items, next_cursor}` | `json`, `jsonl`, `table` |
| `rows` | a stream of rows, such as an export | `jsonl` |

Some Commands offer fewer: `spider commands` itself is `json` or `table`. The `csv` format arrives with `050-add-query-and-segments`.

- **`json`:** compact JSON, no whitespace between tokens, then `\n`.
- **`jsonl` (JSON Lines):** one compact JSON object per line, each followed by `\n`. For a list it is one line per item, without the envelope. For rows it is one line per row, written and flushed as soon as the row is made, so a reader can process a long export while it runs.

  A list Command whose items are `{"n":1}`, `{"n":2}`, … with `--format jsonl --limit 2` prints:

  ```
  {"n":1}
  {"n":2}
  ```
- **`table`:** a table for people to read. Its layout is not a contract, so agents should never parse it. On a terminal it fits the terminal's width; otherwise it is 120 columns wide, so it looks the same everywhere.

## Lists: paging, fields and cursors

A list Command prints one page of its items. The examples use a list whose items are `{"n":1,"sq":1}` to `{"n":5,"sq":25}`, whose fields are `n` and `sq`, and whose default field is `n`.

- **The envelope** with `--format json`:
  - `total`: how many items match
  - `items`: at most `--limit` items
  - `next_cursor`: an opaque string for the next page, or `null` on the last page
- **`--limit`** is 50 by default, and takes 0 to 1000. `--limit 0` prints only the count, with `"items":[]` and `"next_cursor":null`. Any other value is `invalid_value`.
- **Order:** items always come in the same order, so the same request on unchanged data prints the same bytes.

```
spider <list Command> --limit 2
```

```json
{"total":5,"items":[{"n":1},{"n":2}],"next_cursor":"eyJ2IjoxLCJxIjoiMzBiZDUwNzRkMzlkZmY4MSIsImsiOjJ9"}
```

### Cursors

Pass `next_cursor` back with `--cursor` until it is `null`. That prints every item exactly once.
- A cursor works only for the Command, arguments and filters that made it. `--limit`, `--fields` and `--format` may change between pages.
- Any other cursor fails with `invalid_cursor`: one from a different request, such as a different filter, and one that was altered or truncated.
- A cursor uses only `A`–`Z`, `a`–`z`, `0`–`9`, `-` and `_`, so it needs no quoting in a shell.

```json
{"level":"error","code":"invalid_cursor","message":"The cursor was not made by this request, or it was altered.","hint":"Pass the next_cursor of the same request, or leave out --cursor to start again.","details":{}}
```

With `jsonl` and `table` there is no envelope. When more items exist than were printed, the info line `more_items` on stderr gives the `total` and the `next_cursor`. With `--limit 0` it is the only place the total appears, and its `next_cursor` is `null`. With `--format jsonl --limit 2`:

```json
{"level":"info","code":"more_items","message":"2 of 5 items printed.","hint":"Pass --cursor with details.next_cursor for the next page.","details":{"total":5,"next_cursor":"eyJ2IjoxLCJxIjoiMzBiZDUwNzRkMzlkZmY4MSIsImsiOjJ9"}}
```

### Fields

- `--fields sq,n` gives each item exactly those keys, in that order: `{"sq":1,"n":1}`.
- `--fields all` gives every available field, in the Command's order: `{"n":1,"sq":1}`.
- Spaces around a name are ignored, and a name given twice counts once, at its first place: `--fields " sq , n,sq"` is `--fields sq,n`. An empty name, as in `--fields n,,sq`, is `invalid_value`.
- Without `--fields`, the Command's default fields apply. `spider commands` lists the available and default fields of every list Command.
- An unknown field fails with `unknown_field`, which names the field and the available ones:

```json
{"level":"error","code":"unknown_field","message":"This Command has no field size.","hint":"Use --fields with any of: n, sq, or all.","details":{"field":"size","available":["n","sq"]}}
```

## Diagnostics

Errors, warnings and info lines are JSON objects, one per line on stderr. Each has exactly these keys:

| Key | Value |
|---|---|
| `level` | `error`, `warning` or `info` |
| `code` | lowercase snake_case, such as `usage_error` |
| `message` | what happened, for people |
| `hint` | what to do about it, or `null` |
| `details` | an object with data for agents, possibly `{}` |

- A failing Command writes exactly one error, as its last line on stderr.
- Warnings and info lines never change the exit code.
- Errors found while parsing the command line use the same shape: `usage_error` for an unknown Command, an unknown flag or a missing argument, and `invalid_value` for a value that is not allowed.
- An unexpected failure is `internal_error` with exit code 70, and `details.traceback` holds the Python traceback. It is a bug in the tool; no raw traceback ever reaches stderr.
- An error or warning inside a result, such as an entry of a `warnings` list, has the same shape.
- **Written as they happen:** every stderr line, diagnostic or progress event, is written whole and flushed at once, so an agent reading a running Command sees a warning when it happens, not when the Command ends. Lines appear in the order they were reported.

```
spider nosuchcommand
```

```json
{"level":"error","code":"usage_error","message":"No such command 'nosuchcommand'. Did you mean 'commands'?","hint":null,"details":{}}
```

## Progress events

A Command that reports progress writes each event to stderr as one JSON line, flushed at once:

```json
{"event":"progress","ts":"2026-09-27T14:03:12.345Z","data":{"crawled":3}}
```

- `event` names the event, `ts` is the UTC time with milliseconds, and `data` is an object.
- Events and diagnostics share stderr. Tell them apart by the key: an event has `event`, a diagnostic has `level`.
- stdout never carries events, and there is no result event: the result goes to stdout once, when the Command ends.
- `spider commands` marks the Commands that report progress with `"events":true`.

## Partial results

Some failures still have a result worth reading, such as a Crawl that stopped part way. Such a document Command:
- prints its result on stdout
- writes exactly one error, as its last line on stderr
- exits with that error's exit code

```json
{"state":"failed"}
```

Every other failing document or list Command leaves stdout empty, so for those an agent can rely on this: a non-zero exit code with a JSON result on stdout means a partial result, and the error on stderr says what went wrong. A rows Command is different: the rows written before a failure stay on stdout.

## The schema of a crawl file

`spider schema [TABLE]` lists the public tables of a crawl file, with their columns. It is a list Command (`json`, `jsonl` and `table`, `--limit` 50 by default), and it needs no Workspace and no Crawl. Its JSON result starts with `schema_version`, the tool's schema version, before `total`:

```
spider schema seeds --fields name
```

```json
{"schema_version":1,"total":1,"items":[{"name":"seeds"}],"next_cursor":null}
```

`jsonl` and `table` print the items only, so an agent that needs `schema_version` reads the `json` result. Each item has `name`, `kind`, `description` and `columns`; each column has `name`, `description`, `type`, `nullable`, `primary_key`, `references`, `format` and `values`. Tables are listed in the order of the change that added them. An unknown TABLE fails with `unknown_table` (exit code 2), whose `details.tables` lists the tables. [schema.md](schema.md) documents the same tables for people.

## Selecting a Crawl

Every Command that reads a Crawl takes the global flag `--crawl latest|<id>|<path>`, with the default `latest`. `spider commands` describes it with `"global":true` and `"default":"latest"`. What each value selects, and its errors (`no_crawls`, `crawl_not_found`, `crawl_file_invalid` and `invalid_value`), are in [crawl-store.md](crawl-store.md). The first Commands that read a Crawl arrive with `050-add-query-and-segments`.

## Exit codes

The meaning of a code never changes. Codes 9 to 63 are reserved.

| Code | Name | Meaning |
|---|---|---|
| 0 | `ok` | success |
| 1 | `failed` | the Command ran but could not do everything asked; the error says what |
| 2 | `usage` | the command line is wrong: an unknown Command, flag or name, or a missing or invalid value |
| 3 | `config` | `spider.toml` or a setting is invalid |
| 4 | `not_found` | a Workspace, Crawl or item named on the command line does not exist |
| 5 | `busy` | another process holds the Crawl |
| 6 | `incompatible` | the crawl file cannot be used by this version |
| 7 | `io` | reading or writing a file or folder failed |
| 8 | `network` | the network or a required host cannot be reached |
| 70 | `internal` | an unexpected failure, which is a bug in the tool |
| 130 | `interrupted` | stopped with Ctrl+C |

Every error code maps to exactly one exit code:
- `usage_error`, and every code that starts with `invalid_` or `unknown_`, map to 2.
- Every code that ends with `_not_found`, and `no_crawls`, map to 4.

An agent can branch on the exit code alone: 1 means the operation failed, 70 means the tool has a bug, and 130 means someone pressed Ctrl+C. An interrupt is never reported as a bug: it is `interrupted`, with exit code 130.

### The diagnostic codes

Every code is declared once, with its level, its exit code and a description, and `spider commands` lists them under `diagnostics`. A Command never reports a code that is not declared. The codes of this change:

| Code | Level | Exit code | Meaning |
|---|---|---|---|
| `usage_error` | error | 2 | an unknown Command or flag, a missing argument, or a global flag before the Command name |
| `invalid_value` | error | 2 | a flag or argument value that is not allowed |
| `unknown_field` | error | 2 | a `--fields` name the Command does not have |
| `invalid_cursor` | error | 2 | a `--cursor` made by a different request, or altered |
| `settings_invalid` | error | 3 | `spider.toml` cannot be read or breaks the settings rules |
| `workspace_not_found` | error | 4 | the `--workspace` folder does not exist |
| `workspace_not_writable` | error | 7 | the Workspace folder or its data folder cannot be created or written |
| `internal_error` | error | 70 | an unexpected failure, which is a bug |
| `interrupted` | error | 130 | stopped with Ctrl+C |
| `workspace_nested` | warning | | the new Workspace is inside another Workspace |
| `more_items` | info | | more items exist than were printed |
