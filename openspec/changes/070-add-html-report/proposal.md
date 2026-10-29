## Why

People read Reports, not JSON. The approved model is a hybrid Report: the tool builds a self-contained, offline HTML file with the numbers, charts, Issues and fix guidance, and the agent adds its analysis as Report Notes (ADR-0004). On large sites, one agent cannot analyse everything at once. So the data must also come as compact, per-Report-Section Section Briefs that one subagent per Report Section can work from. The Skill (`080`) is drafted against this contract, so the Report Section ids, the Section Brief JSON and the Report Notes file contract have to be fixed now.

## What Changes

New Commands. They take the `--format` and `--workspace` flags from `010-add-workspace-and-cli-contract`, the `--crawl` option from `015-add-crawl-store`, and `-o` from `050-add-query-and-segments`:

| Command | Flags added by this change |
|---|---|
| `linx report` | `--dest <dir>`, `--segment <name>`, `--notes <dir>`, `--open`, `--top <n>` |
| `linx report brief` | `--section <id>`, `--list`, `--segment <name>`, `--max-bytes <n>` |

- **`report`**: writes one self-contained HTML file that works offline and makes no external requests, plus a folder of CSV files with the full lists. They go to `--dest <dir>`, by default `.openlinx/reports/<crawl id>/`, and a JSON receipt with absolute paths goes to stdout. `-o` redirects the receipt, as for any Command. `--open` opens the Report in the default browser on Windows, macOS and Linux.
- **Fixed Report Sections for v0.1:** `overview`, `response-codes`, `indexability`, `titles`, `meta-descriptions`, `headings`, `canonicals-and-directives`, `content`, `urls`, `images`, `security`, `structured-data` (counts only) and `segments` (only when Segments are defined).
  - Report Section ids are kebab-case, and each maps explicitly to 040's snake_case Rule categories.
  - Each Report Section has key numbers, inline SVG charts, and its Issues with the Rule's description, why it matters, how to fix, and thresholds.
  - Each Issue lists its top N Affected URLs in a table that can be sorted and filtered, with a link to its CSV file.
- **The Health Score** in the header, and per Segment in the `segments` Report Section. The Report's numbers come from the same summary model as `linx summary` (`050`).
- **`report brief --section <id>`**: a compact Section Brief in JSON (counts, Issues with `affected_count`, sample Affected URLs, thresholds), 16 KiB at most by default. **`report brief --list`** lists the Report Sections, whether each applies, their Rule categories and their Issue counts.
- **The Report Notes file contract:** `<dir>/summary.md` holds the executive summary, and `<dir>/<section-id>.md` holds one Report Section's analysis. Notes are rendered as CommonMark with tables, and raw HTML is shown as text. An unknown notes file produces a warning, and a Report Section without notes is rendered without analysis.
- **CSV files** follow 050's CSV policy.
- **Security:**
  - All crawled text is escaped.
  - A Content-Security-Policy allows only the Report's own inline script and style.
  - Notes cannot inject HTML, scripts, remote images or `javascript:` links.
  - The Report never includes the recorded command or config.
- **Labels:** in a Section Crawl, link metrics are labelled "partial". A Crawl whose Crawl State is not `completed` gets a notice that names the state.
- **The end-to-end CI test** on Windows, macOS and Linux: `crawl --detach` → `status` → `issues` → `report`.
- **The table script** is tested at seam 9 with `node --test` in CI.
- **Flags beyond ROADMAP.md:** small ones the Commands obviously need: `report --top`, `report brief --list` and `report brief --max-bytes`.
- **MCP tools:** none here. `090-add-mcp-server` wraps both Commands and returns the same JSON.
- **New dependencies:** Jinja2, for templates with autoescaping (shared with the Skill generator in `080`), and markdown-it-py, for CommonMark notes rendering with raw HTML disabled.

## Capabilities

### New Capabilities
- `reporting`: the `report` and `report brief` Commands, the Report's files, destination and receipt, the fixed Report Sections and their mapping to Rule categories, charts, CSV lists, the Section Brief JSON and its size budget, the Report Notes file contract and its safe rendering, escaping and the offline guarantees, labels for Section Crawls and Crawl States, opening the Report, and the end-to-end test from a detached Crawl.

### Modified Capabilities
- None. The main specs are still empty, and the other v0.1 capabilities are being added in parallel.

## Non-goals

- Report Sections for links, redirects and sitemaps: **v0.2**.
- The diff Report (Crawl Diff): **v0.3**.
- Structured-data validation in the Report (v0.1 shows counts, and validation shows as "not measured"): **v0.3**.
- The white-label Report: **v1.0**.
- PDF output and translated Report labels: **backlog**. Labels are English, and Report Notes may be in any language.
- Analysis written by the tool: never (ADR-0004).

## Impact

- **Depends on:**
  - `050-add-query-and-segments`: the summary model, Segments and `--segment`, the Issue order and the Affected URL order, the CSV policy, and `-o` with `output_not_writable`.
  - `040-add-rules`: the per-Crawl `rules` table with categories, guidance and thresholds, `issues` with `affected_count`, `affected_urls`, and the Health Score.
  - `030-add-page-data`: the `pages` columns, including the structured-data counts.
  - `010-add-workspace-and-cli-contract`: the output contract (receipt, diagnostics, exit codes) and `linx commands`.
  - `015-add-crawl-store`: `--crawl`, crawl metadata (Crawl State, Section Crawl flag) and the Workspace's `.openlinx` directory.
  - `060-add-crawl-control`: `crawl --detach` and `status`, which the end-to-end test drives.
- **Used by:**
  - `080-add-agent-skill`: the Full audit workflow, the Report Section ids read from `linx commands`, and the notes file names.
  - `090-add-mcp-server`: the same JSON. Its inline notes are stored under the Crawl's reports folder.
  - `060-add-crawl-control`: `crawls rm` deletes `.openlinx/reports/<crawl id>/`, whose layout is defined here.
- **Code:** `src/openlinx/report/` (the Report Section registry, ReportModel, Section Briefs, SVG charts, notes rendering, `templates/` and the table script), `src/openlinx/services/report.py` and `src/openlinx/cli/report.py`.
- **Tests:** the seam 9 tests for `templates/table.js`, run with `node --test`, and the end-to-end test in the CI workflow.
- **Files written:** `report[-<segment>].html` and `report[-<segment>]-csv/` in `--dest` (by default `.openlinx/reports/<crawl id>/`). Nothing is written to the crawl store.
- **Docs:** `docs/report.md`, `docs/contracts/section-brief.md` and `docs/contracts/report-notes.md`.
