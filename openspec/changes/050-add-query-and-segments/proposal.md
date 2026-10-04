## Why

After a Crawl, the crawl store holds everything, but agents and people still need stable, token-efficient ways to ask it questions: an overview, filtered Page lists, one URL in detail, the Issues, ad-hoc SQL and bulk export. Large sites also need to be read part by part through Segments, without crawling again. The Report (`070`), the Skill (`080`) and the MCP server (`090`) all build on these outputs, so their shapes have to be fixed as contracts now.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships `summary`, `pages`, `page` and `issues`. **Deferred to v0.2:** `sql`, `export`, Segments (the `segments` capability, `--segment`, the per-Segment breakdown in `summary`), `page --html`, the `--where` operators beyond comparisons, `contains`, `is [not] null` and `and`, and the whole `cli-contract` delta (`--format csv`, the CSV policy, `--no-bom` and `-o`).
>
> **End-to-end test in v0.1:** a cross-OS CI test, a foreground `crawl` → `issues` on Windows, macOS and Linux, is the last part of the thin slice (050-issues).

New Commands, all read-only. They take `--format` (`json`, `jsonl` and `table`) and the `--workspace` flag from `010-add-workspace-and-cli-contract`, the `--crawl` option (`latest|<id>|<path>`) from `015-add-crawl-store`, and the `csv` format, `--no-bom` and `-o` from this change:

| Command | Flags added by this change |
|---|---|
| `spider summary` | `--segment <name>`, `--top <n>` |
| `spider pages` | `--where <expr>`, `--sort <keys>`, `--segment <name>`, plus 010's `--fields`, `--limit` and `--cursor` |
| `spider page <url>` | `--html`, `--headers` |
| `spider issues` | `--type <list>`, `--priority <list>`, `--category <list>`, `--segment <name>`, plus 010's paging flags |
| `spider issues <rule-id>` | `--where`, `--sort`, `--segment <name>`, plus 010's `--fields`, `--limit` and `--cursor` |
| `spider sql "<query>"` | `--file <path>`, `--limit <n>`, `--timeout <seconds>` |
| `spider export <view>` | `--where`, `--fields`, `--sort`, `--segment <name>`; `--format jsonl` (the default) or `csv` |

Global flags added by this change to the CLI contract: `--format csv`, `--no-bom` and `-o/--output <file>`.

- **CSV and output files (`cli-contract`)**: moved here from `010-add-workspace-and-cli-contract` (maintainer decision, 2026-10-01).
  - The `csv` format for document, list and rows Commands, including the `more_items` info line, and `csv` in the formats that `spider commands` lists.
  - The CSV policy: UTF-8 with a byte-order mark (`--no-bom` leaves it out), RFC 4180 with CRLF, and formula neutralisation. There is one CSV writer for everyone: `export` here and the Report CSV files of `070-add-html-report`.
  - `-o/--output <file>`: an atomic replacement that happens only on success, the info line `output_written`, and `output_not_writable` (exit code 7).
- **`summary`**: Crawl metadata (the Crawl State and the Section Crawl flag, with link metrics labelled partial), URL counts by `status_classes`, Indexability, content type and Crawl Depth, response-time statistics, the Health Score, Issue counts by Issue Type × Priority, the top Issues, and a per-Segment breakdown. Its JSON shape is a versioned contract (`summary_version: 1`) that the Report reuses.
- **The `--where` filter language**: comparisons, `~` / `!~` regex, `contains`, `in`, `is [not] null`, `and` / `or` / `not` and parentheses over the column names that `spider schema` lists. Nulls follow two-valued logic, and unknown columns fail with `unknown_column` and close-match suggestions.
- **`pages`**: multi-key `--sort` (a `-` prefix sorts descending), and stable keyset paging inside 010's paging envelope.
- **`page <url>`**: JSON with every column for one URL, its Segment, its Issues, its Redirect Chain and its link counts. `--html` adds `html` (the stored HTML as text) and `encoding`. `--headers` adds the recorded response headers, with cookie values redacted.
- **`issues`** and **`issues <rule-id>`**: the Issue list with `affected_count`, and one Issue's guidance with its paged Affected URLs.
- **`sql`**: runs exactly one `SELECT`/`WITH` statement. Anything else is refused. Results are capped by a default row limit and a timeout.
- **`export`**: the views `pages`, `links`, `resources`, `issues` and `affected-urls`, streamed as NDJSON rows, or as CSV under this change's CSV policy. `-o` works as this change defines it, and there is no receipt. The `resources` view is defined over the `urls` and `links` tables.
- **Segments**: an ordered `[segments]` table in `spider.toml` that maps each name to a `--where` expression. Definitions are checked when settings load (`settings_invalid`). The first match wins, and Segments are applied at query time. There is a `--segment` flag and a `segment` field.
- **Flags beyond ROADMAP.md**: small ones that the Commands obviously need: `summary --top`, `issues --category`, `issues <rule-id> --where/--sort`, `sql --file/--limit/--timeout`, and `export --where/--fields/--sort`.
- **MCP tools**: none here. `090-add-mcp-server` wraps these Commands and returns the same JSON.

## Capabilities

### New Capabilities
- `querying`: the `summary`, `pages`, `page`, `issues`, `sql` and `export` Commands, the `--where` filter language, sorting, the export views, and the summary JSON contract.
- `segments`: Segment definitions in `spider.toml` and their check at load time, first-match membership computed at query time, the `--segment` flag, the `segment` field, per-Segment Issue counts and Health Score, and the per-Segment breakdown in `summary`.

### Modified Capabilities
- `cli-contract`: from `010-add-workspace-and-cli-contract`, which is archived before this change starts. This change only adds requirements: the `csv` format, the CSV policy, writing output to a file with `-o`, the global flags `--no-bom` and `-o/--output`, and the diagnostics `output_not_writable` and `output_written`.

## Non-goals

- `links <url> --in|--out`, `redirects` (per-hop headers and timing) and `sitemaps`: **v0.2**.
- Link Score values stay null until **v0.2**. Near-Duplicate and structured-data validation columns stay null until **v0.3**.
- Recomputing Issues after thresholds change (`rules apply`): **v0.2**.
- `duplicates`, `structured-data`, `diff A B` and Custom Extraction columns: **v0.3**.
- xlsx export: **v1.0**.
- REST API and web UI: **backlog**.
- Any SQL that writes to a crawl store: never. The store is changed only by the Crawl's writer.
- MCP tool definitions: `090-add-mcp-server` (v0.1.1). The HTML Report and Section Briefs: `070-add-html-report` (v0.2).

## Impact

- **Depends on:**
  - `010-add-workspace-and-cli-contract`: Workspace discovery and `spider.toml` loading, including the settings check that covers `[segments]`. Also the output contract: the formats `json`, `jsonl` and `table`, the paging envelope with `--fields` and cursors, the global flags, diagnostics, exit codes and `spider commands`.
  - `015-add-crawl-store`: the `--crawl` option, crawl metadata, read-only access, `spider schema` and `docs/schema.md`.
  - `020-add-crawl-core`: the `urls` table, the Link types, the Section Crawl flag and Crawl Depth.
  - `022-add-fetch-policy`: Redirect Chain hops, the `response_headers` table (with cookie values redacted) and Resource status and size.
  - `030-add-page-data`: the `pages`, `links` and `page_sources` tables and the link counts.
  - `040-add-rules`: the per-Crawl `rules` table, `issues` (with `affected_count`), `affected_urls`, the Health Score function and `rule_not_found`.
- **Used by:** `070-add-html-report` (the summary model, the export row serialisers, Segments, the CSV writer and `-o`), `080-add-agent-skill` (command metadata and recipes) and `090-add-mcp-server` (the same JSON).
- **Code:** `src/spider/query/` (the where language, sorting and paging, Segments, export views), `src/spider/services/query.py`, the query command modules in `src/spider/cli/`, and the CSV writer, `NoBomOpt` and `OutputOpt` in 010's output layer `spider.output`.
- **Data:** no new tables and no schema version bump. Segments are never stored.
- **Dependencies:** no new third-party packages.
- **Docs:** `docs/querying.md`, `docs/segments.md`, `docs/contracts/summary.md`, and the `csv` format, the CSV policy and `-o` in `docs/cli.md`.
- **Tests:** 010's hand-written contract JSON in `tests/contract/commands/` gets `csv`, `--no-bom` and `--output` in the `init` entry.
