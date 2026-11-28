# Querying a Crawl

## Read-only SQL

Use `linx sql` to read one snapshot of a Crawl. Run `linx schema` to list tables
and `linx schema pages` to see the columns of `pages`. The same public tables
are listed in the [crawl-file schema](schema.md).

```sh
linx sql "SELECT count(*) AS page_count FROM pages"
linx sql --file report.sql --crawl 20260927-140312-k3f9
```

Supply exactly one query argument or `--file PATH`. Query files use UTF-8 and
may start with a byte-order mark. A relative file path starts at the current
folder. [Crawl selection](crawl-store.md#selecting-a-crawl) uses `--workspace`
and `--crawl`. By default it selects the Crawl that started last.

The Store opens the Crawl read-only. It accepts one read-only `SELECT` or
`WITH` statement. It refuses the following to protect the crawl file and keep
the read on its own connection and snapshot.

- `INSERT`, `UPDATE`, `DELETE` and a `WITH` statement that changes data
- `CREATE`, `DROP`, `ALTER`, `REINDEX`, `ANALYZE` and `VACUUM`
- `ATTACH`, `DETACH`, `PRAGMA` and transaction statements such as `BEGIN`,
  `COMMIT` and `ROLLBACK`
- A second statement and any attempt to load an extension

The default output is one JSON document. `--format table` presents the same
keys and values for people.

```json
{"columns":["page_count"],"rows":[[12]],"row_count":1,"truncated":false,"limit":1000}
```

| Key | Value |
|---|---|
| `columns` | Result column names in query order, including any duplicates. |
| `rows` | Arrays of values in the same order. Each BLOB becomes `{"blob_bytes": n}`, where `n` is its byte length. |
| `row_count` | Number of returned rows. |
| `truncated` | `true` if the query produced more rows than the limit. |
| `limit` | The requested `--limit`, from 1 to 100,000. The default is 1,000. |

SQLite REAL positive infinity becomes `{"real":"Infinity"}` and negative
infinity becomes `{"real":"-Infinity"}`. Finite REAL values stay JSON
numbers, SQL NULL stays `null`, and TEXT values such as `"Infinity"` and
`"-Infinity"` stay strings.

`--timeout` sets the time budget for executing the statement and fetching
results, in seconds. The default is 30. Use a finite nonnegative number.
A zero budget times out immediately.

| Code | Exit | Meaning |
|---|---:|---|
| `usage_error` | 2 | Supply one query source. |
| `invalid_value` | 2 | An invalid option value or a query file that cannot be read as UTF-8. File errors give the path in `details.file`. |
| `sql_not_allowed` | 2 | The statement is outside the read-only subset. |
| `sql_error` | 2 | SQLite rejected the query. The diagnostic includes SQLite's message. For unknown tables or columns, `details.suggestions` lists close matches and the hint points to `linx schema`. |
| `sql_timeout` | 1 | The query exceeded its time budget. |
