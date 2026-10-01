## Context

See proposal.md (Why) for motivation. Everything the Report shows comes from the **Query Service** of `050-add-query-and-segments`:
- the `SummaryModel` msgspec Structs
- Segment resolution
- the Issue order and the order of Affected URLs (Unique Inlinks, descending)

CSV files are written with the CSV serialiser of `050-add-query-and-segments`, which applies its CSV policy. Rule texts, categories and thresholds come from the Crawl's `rules` table (`040-add-rules`), and the Crawl State and the Section Crawl flag from the crawl metadata (`015-add-crawl-store`, `020-add-crawl-core`).

The **Report Service** (`src/spider/services/report.py`) builds a ReportModel once per invocation. The HTML renderer and the Section Brief builder both read that model, so the Report and its briefs cannot disagree.

`080-add-agent-skill` is drafted against three things: `report brief --section <id>` with its accepted values listed by `spider commands`, one subagent per Report Section, and `report --notes <dir>`. `090-add-mcp-server` stores inline notes under the Crawl's reports folder, and `060-add-crawl-control`'s `crawls rm` deletes that folder.

## Goals / Non-Goals

**Goals:**
- One HTML file that opens offline from `file://`, can be emailed, and cannot run crawled content or notes as code.
- One Report Section registry that defines the ids, titles, order, Rule categories, charts and extra table columns, and drives the HTML, the briefs and `report brief --list`.
- Section Briefs that always fit their byte budget and are deterministic.
- Byte-identical output for identical input, apart from the generation time, so golden tests and diffs are possible.
- The end-to-end proof that a detached Crawl turns into a Report on all three OSes.

**Non-Goals:**
- Client-side rendering, charting libraries and web fonts.
- Analysis, prioritisation or wording chosen by the tool (ADR-0004).
- Output mechanics that other changes own: diagnostics (010), and the CSV policy and `-o` (050).
- PDF, translations and white-labelling (see proposal Non-goals).

## Decisions

### D1. One Report Section registry drives the HTML, the briefs and the list
Each registry entry is a Python record:
- the kebab-case id, title and order
- the snake_case 040 category ids it shows:

  | Report Section | Categories |
  |---|---|
  | `response-codes` | `response_codes` |
  | `titles` | `titles` |
  | `meta-descriptions` | `meta_descriptions` |
  | `headings` | `headings` |
  | `canonicals-and-directives` | `canonicals` and `directives` |
  | `content` | `content` |
  | `urls` | `urls` |
  | `images` | `images` |
  | `security` | `security` |
  | `overview`, `indexability`, `structured-data`, `segments` | none |

- chart builders
- extra Affected URL columns (Title 1, Meta Description 1 or H1-1)
- a key-number builder that returns an ordered `{key: value}`

`report brief --list`, the `--section` parameter type, the HTML sections and `counts` in the briefs all iterate the registry.
- *Alternative:* separate templates and brief builders per Report Section. The numbers would drift apart, which is exactly what the "Counts equal the Report" scenario guards against.

### D2. The ReportModel is the SummaryModel plus one model per Report Section, from one snapshot
The Report Service opens one read transaction and builds:
- the summary through 050, for the whole Crawl or for `--segment`
- for each registry entry, its Issues (with top-N Affected URLs and samples), key numbers and chart data

Only whitelisted fields go in: the summary's `crawl` member, and the Rule texts and thresholds of the Crawl's `rules` table. The recorded command and config are never read into the model, so they cannot leak, even in the redacted form that 015 stores.
- *Alternative:* the templates query the store directly. That scatters queries around, breaks snapshot consistency, and makes leaks possible.

### D3. Jinja2 with autoescaping everywhere
Templates live in `src/spider/report/templates/` and use an `Environment(autoescape=True, undefined=StrictUndefined)`. Only two producers may insert markup (`Markup`), and both escape their own inputs and are tested at the Report seam:
- the notes renderer (D4)
- the SVG chart builder (D5)

Rule guidance is rendered as escaped plain text, with one paragraph per blank-line-separated block, so 040's texts make no rendering assumptions. Jinja2 is also used by 080's Skill generator.
- *Alternatives:* building strings by hand makes it easy to forget one escape. Mako and Chameleon are less familiar and bring no benefit here.

### D4. Notes use markdown-it-py with raw HTML disabled
The renderer is `MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")`, customised as follows:
- `validateLink` allows only `http:`, `https:` and `mailto:`
- the `image` rule renders the alt text as plain text, so nothing is ever fetched
- the heading renderer adds 2 to the level, capped at `h6`
- the link renderer adds `rel="noopener noreferrer"`

Files are decoded by BOM sniffing: UTF-8-SIG, then UTF-16 LE/BE by BOM, then UTF-8 with `errors="replace"`, which raises the `notes_encoding` warning. File names are compared case-folded against `summary` and the registry ids. Unknown files get a close-match hint via `difflib`.
- *Alternatives:*
  - mistune, whose CommonMark coverage is looser.
  - Python-Markdown, which is not CommonMark and cannot cleanly disable raw HTML.
  - Rendering raw HTML and sanitising it afterwards (bleach is deprecated). Never producing HTML from the input is stronger than cleaning it later.

### D5. Charts are our own small SVG builder
The builder has four chart forms:
- a vertical bar chart: status classes, content types, Crawl Depth and the response-time histogram
- a horizontal bar chart: Top Issues, Affected URLs per Issue, Indexability Status, Health Score by Segment and structured data types
- a stacked bar: Indexability
- a 3×3 matrix: Issue Type × Priority

Rules:
- Only presentation attributes are used, never `style` attributes (CSP).
- IDs are derived from the Report Section id and the chart index, never random.
- Numbers are formatted in English.
- Each chart has `<title>` and `<desc>` (`label: value; …`).
- An empty dataset gives `<p>No data</p>`.
- *Alternatives:* matplotlib is a heavy import, has font issues, random ids and large SVGs. pygal needs external JS for tooltips. Vega-Lite needs a JS runtime or a CDN.

### D6. Offline by construction, with a CSP as a second line of defence
The Report has one `<style>` and one `<script>`, both inline. The `<meta http-equiv="Content-Security-Policy">` value is `default-src 'none'; style-src 'sha256-<css>'; script-src 'sha256-<js>'; base-uri 'none'; form-action 'none'`, with both hashes computed at render time. Browsers apply a meta CSP to `file://` documents. Escaping remains the primary defence, and the CSP ensures that even an escaping bug cannot load or run anything.

### D7. The table script is small, vanilla and testable in Node
`src/spider/report/templates/table.js` is about 3 KB of ES2017. It holds the pure functions `compareCells`, `sortRows` and `filterRows`, plus a little DOM glue that runs on `DOMContentLoaded`. When `module` exists, it exports the pure functions, so the seam 9 tests under `node --test` load the same file that is embedded in the Report. Tables work without the script (progressive enhancement).

### D8. The destination folder, the receipt, and how files are replaced
- **Destination:** `--dest <dir>`, by default `<Workspace's .spider directory>/reports/<crawl id>/`. The folder holds `report[-<segment>].html` and `report[-<segment>]-csv/`. The Report stays next to the Crawl it describes, `crawls rm` (060) deletes the folder with the Crawl, and 090 stores inline notes inside it.
- **Receipt:** a JSON document on stdout with the absolute paths. `-o` redirects it, as 050 defines for every Command, so `-o` never names the HTML file.
- **Replacement:** everything is built in a sibling temporary folder. Then the old CSV folder is renamed aside, the new one is renamed into place, the old one is deleted, and finally the HTML is moved into place with `os.replace`. The HTML goes last, so an old HTML file never points to a missing CSV folder.
- **Failure:** earlier steps are rolled back, the temporary folder is removed, and the command fails with 050's `output_not_writable`, naming the path. On Windows, an open file makes the folder rename fail with a sharing violation.
- **Transient locks:** renames are retried up to 5 times within 1 second, for antivirus scanners and indexers.
- *Alternatives:*
  - Using `-o` for the HTML path, which contradicts G4, where `-o` always carries the stdout bytes.
  - The current directory (`./report.html`), which clutters the project and makes Crawls overwrite each other.

### D9. Opening the Report without the `webbrowser` module
- **Windows:** `os.startfile(path)`.
- **macOS:** `subprocess.Popen(["open", path])`.
- **Linux:** `subprocess.Popen(["xdg-open", path], start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)`, only when `DISPLAY` or `WAYLAND_DISPLAY` is set.

Nothing is awaited. A missing opener or an `OSError` becomes the warning `open_failed`. Reading `DISPLAY` and `WAYLAND_DISPLAY` detects a desktop session. They are not settings of the tool, so the "no environment variables" rule (G7) does not apply.
- *Alternative:* the `webbrowser` module can start a console browser such as lynx or w3m on headless Linux, which takes over the agent's terminal.

### D10. Section Briefs keep to their budget with a fixed reduction loop
The builder serialises with orjson, compares the byte length with `max_bytes`, and applies the four spec steps in order until the brief fits. Step 1 lowers all samples together (5 → 4 → … → 1). Steps 3 and 4 work from the last Issue backwards. The minimum budget of 8,192 bytes always leaves room for the skeleton: at most 10 Seeds of 300 characters each, the counts, the rule ids and `omitted_issues`.

### D11. `--section` is a Choice that raises our own errors
A Click `Choice` subclass exposes the thirteen ids to `spider commands --format json`, which 080's "Report Section ids are listed" scenario reads. Its `convert` raises `unknown_section`, with `details.suggestions` and `details.accepted`, instead of Click's usage text. A missing `--section`/`--list`, or both of them, raises 010's `usage_error` with `details.accepted`.

### D12. Deterministic output
Every ordering is explicit, numbers are formatted in fixed ways, and ids come from the registry. The only varying value is the generation time, which comes from the injectable clock (a boundary double).

### D13. The end-to-end CI test
One pytest test, marked `e2e`, runs on the Windows, macOS and Linux CI jobs. It starts the local fixture site, then runs these as real subprocesses of the installed CLI:
1. `spider crawl <site>/ --detach` (060)
2. `spider status`, polled every second for up to 120 seconds until it reports `completed`
3. `spider issues`
4. `spider report`

It then parses the HTML named by the receipt. No doubles are used.
- *Alternative:* in-process `CliRunner` calls. They would not exercise the detached process, the control rows or the Windows process flags, which are exactly what this test protects.

## Test seams

This change is tested at these seams from docs/testing.md:

- **Report (7):** Reports are built from real crawl stores (050's `crawl_store` factory, which writes documented tables only) and from Crawls of the fixture site. The generated HTML is parsed with selectolax, already a dependency, with no browser. The tests check Report Sections, ids, `data-metric` values, `svg` titles and descriptions, escaping, the CSP, notes, and the brief's JSON.
- **CLI (1):** the receipt, exit codes, diagnostics and file locations of `report` and `report brief`. Real subprocess runs on Windows check non-ASCII folders and locked CSV files. The end-to-end test (D13) uses real subprocesses on all three OSes.
- **Services and store API (2):** the Report Service's ReportModel and briefs, and their consistency with `SummaryModel`.
- **HTTP fixture site (3):** the end-to-end runs, over "3+6" data that a real Crawl leaves behind.
- **Report script (9):** the table script's pure functions under `node --test`, with no npm packages. 000 sets up Node in CI. A pytest wrapper runs the Node tests, skips when `node` is missing locally, and fails in CI when it is missing.

**Boundary doubles** (the docs/testing.md list):
- **Processes:** the OS process-spawn call (`os.startfile`, `subprocess.Popen`) behind `--open`.
- **Clock:** the injectable clock behind `#generated-at`.

The desktop-session variables are set in the test environment as input, and file locks are real, on Windows.

## Risks / Trade-offs

- **The CSP could be ignored by some viewer.** → Escaping is the primary defence and is tested with attack strings. The CSP is only a second layer.
- **A third-party Markdown library renders untrusted notes.** → `html=False`, a link allowlist, an image override and attack-string tests at the Report seam. markdown-it-py is pinned to a major version.
- **The category mapping can drift from 040.** → The scenarios "The category mapping" and "Every Rule category has a Report Section" fail as soon as 040 adds or renames a category.
- **The CSV folder can be large for huge Crawls,** since the full lists go into it. → The rows are streamed through 050's CSV serialiser. The HTML stays bounded by `--top`.
- **Windows locks from Excel, antivirus scanners or indexers.** → The swap with rollback, a short retry, and `output_not_writable` naming the file.
- **The end-to-end test is slow and can be flaky** (process start, polling). → One fixture site with few Pages, a 120-second cap, and polling of `status` rather than fixed sleeps.

## Migration Plan

None. The change writes no store data. Report files live outside the crawl store and can be deleted at any time; `crawls rm` deletes them with their Crawl.

## Open Questions

- Should `report` pick up a default notes folder such as `reports/<crawl id>/notes/`, where 090 stores inline notes, when `--notes` is omitted? This would be additive.
- CONTEXT.md allows a Report Section to cover one Segment. v0.1 has one `segments` Report Section plus `report --segment`. Should per-Segment Report Sections come later?
- Should the header show Scope details (subfolder, `--include` patterns) for Section Crawls? This needs a secret-free Scope summary from 020 and is additive.
- How much print styling should the Report get, so that "Save as PDF" in a browser looks good until the PDF backlog item?
- Should notes files have a size limit, for example 256 KiB with a warning?
