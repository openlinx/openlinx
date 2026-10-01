# The CLI contract

How every `spider` Command talks to agents and people. The spec is `openspec/changes/010-add-workspace-and-cli-contract/specs/cli-contract/spec.md` until the change is archived, then `openspec/specs/cli-contract/spec.md`. Terms follow [CONTEXT.md](../CONTEXT.md).

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

Every Command has an output kind, which `spider commands` lists as `output`. The kind decides the formats the Command offers:

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
- An error or warning inside a result, such as an entry of a `warnings` list, has the same shape.

```
spider nosuchcommand
```

```json
{"level":"error","code":"usage_error","message":"No such command 'nosuchcommand'. Did you mean 'commands'?","hint":null,"details":{}}
```

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

An agent can branch on the exit code alone: 1 means the operation failed, 70 means the tool has a bug.
