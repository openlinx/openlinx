## Purpose

Turns a Crawl into a Report for people: one self-contained, offline HTML file with fixed Report Sections, charts, Issues with fix guidance, CSV files with the full lists, and the agent's Report Notes. It also gives agents compact Section Briefs to analyse when they write those notes.

## ADDED Requirements

### Requirement: Report files

`spider report` SHALL write the files of one Report into a destination folder:
- **Files:** an HTML file `report.html` and a folder `report-csv`. With `--segment <name>`, they are `report-<name>.html` and `report-<name>-csv`.
- **Destination:** the folder is `--dest <dir>`, created if it is missing. Without `--dest`, it is `reports/<crawl id>/` inside the Workspace's `.spider` directory.
- **The default folder** holds only what is written for that Crawl's Reports, and `060-add-crawl-control`'s `crawls rm` deletes it together with the Crawl.
- **Replacement:** running `report` again with the same destination SHALL replace the HTML file and the whole CSV folder. If the files cannot be replaced, the command SHALL fail with `output_not_writable` (exit code 7, `010-add-workspace-and-cli-contract`), whose message names the path, and leave the previous Report unchanged.

#### Scenario: Default location
- **WHEN** the Workspace's `.spider` directory is `<tmp>/site/.spider`, the latest Crawl has the id `<id>`, and `spider report` runs
- **THEN** the file `<tmp>/site/.spider/reports/<id>/report.html` exists

#### Scenario: Default CSV folder
- **WHEN** the Workspace's `.spider` directory is `<tmp>/site/.spider`, the latest Crawl has the id `<id>`, and `spider report` runs
- **THEN** the folder `<tmp>/site/.spider/reports/<id>/report-csv` exists

#### Scenario: Location of a Segment Report
- **WHEN** the Segment `blog` is defined and `spider report --segment blog` runs for the Crawl `<id>`
- **THEN** the files `reports/<id>/report-blog.html` and `reports/<id>/report-blog-csv/issues.csv` exist inside the Workspace's `.spider` directory

#### Scenario: --dest names the folder
- **WHEN** `<tmp>/out` does not exist and `spider report --dest <tmp>/out` runs
- **THEN** the file `<tmp>/out/report.html` and the folder `<tmp>/out/report-csv` exist

#### Scenario: Re-running removes CSV files that no longer apply
- **WHEN** `spider report --segment blog` wrote `report-blog-csv/title-missing.csv`
- **AND** the `blog` definition is changed so that none of its Pages lacks a title, and `spider report --segment blog` runs again
- **THEN** `report-blog-csv/title-missing.csv` no longer exists

#### Scenario: Windows folder with spaces and non-ASCII characters
- **WHEN** on Windows, `spider report --dest "<tmp>\Отчёты клиента"` runs as a real subprocess
- **THEN** the file `<tmp>\Отчёты клиента\report.html` exists, and the receipt's `path` is exactly that absolute path

#### Scenario: A locked CSV file on Windows leaves the previous Report intact
- **WHEN** on Windows, a previous `spider report` wrote `report.html` and `report-csv/issues.csv`, and another process holds `report-csv/issues.csv` open
- **AND** `spider report` runs again
- **THEN** the exit code is 7, the error has the code `output_not_writable` and a message that contains the path of `issues.csv`, and `report.html` is byte-identical to before

### Requirement: Report receipt

`spider report` SHALL print one JSON object on stdout, the receipt: `{path, csv_dir, crawl_id, segment, health_score, sections, notes, warnings, opened}`. `-o <file>` SHALL write the receipt to that file instead, following the rule of `010-add-workspace-and-cli-contract`.
- `path` and `csv_dir` are absolute paths in the operating system's native form.
- `health_score` is the value of `health_score.score` in `spider summary` for the same Crawl and Segment.
- `sections` lists the rendered Report Section ids in Report order.
- `notes` is `{dir, applied, missing}`. `dir` is the absolute notes folder, or `null` without `--notes`. `applied` lists the notes that were rendered, `summary` first and then the Report Section ids in Report order. `missing` lists, in the same order, `summary` and the applicable Report Section ids that have no notes file.
- `warnings` lists the warnings as the diagnostic objects of `010-add-workspace-and-cli-contract` (`{level, code, message, hint, details}`, with `level` `warning`). Each warning is also written to stderr as a diagnostic line.
- `opened` tells whether the Report was handed to a browser.

A Report written with warnings SHALL still exit with code 0.

#### Scenario: Receipt without notes
- **WHEN** no Segments are defined, the Crawl's Health Score is 80, and `spider report` runs without `--notes`
- **THEN** the receipt contains `"health_score": 80`, `"notes": {"dir": null, "applied": [], "missing": ["summary", "overview", "response-codes", "indexability", "titles", "meta-descriptions", "headings", "canonicals-and-directives", "content", "urls", "images", "security", "structured-data"]}`, `"warnings": []` and `"opened": false`

#### Scenario: -o redirects the receipt
- **WHEN** `spider report -o receipt.json` runs
- **THEN** stdout is empty, and `receipt.json` holds a JSON object whose `path` ends with `report.html`

### Requirement: Self-contained offline Report

The HTML file SHALL embed every style, script and chart it uses, and SHALL load nothing from anywhere else: no external scripts, stylesheets, fonts, images, frames or CSS imports. It SHALL contain exactly one `script` element and one `style` element. It SHALL declare a Content-Security-Policy in a `meta` element that starts with `default-src 'none'` and allows only that script and that style, each by its SHA-256 hash. No element SHALL have a `style` attribute or an attribute whose name starts with `on`.

#### Scenario: Nothing is loaded from elsewhere
- **WHEN** the Report of a `completed` Crawl of the local fixture site is parsed
- **THEN** no element has a `src`, `srcset` or `poster` attribute, there is no `link`, `iframe`, `object` or `embed` element, every element with an `href` attribute is an `a` element, and the text of the `style` element contains neither `url(` nor `@import`

#### Scenario: Content-Security-Policy
- **WHEN** the Report is parsed
- **THEN** it has a `meta` element with `http-equiv="Content-Security-Policy"` whose `content` starts with `default-src 'none'`

#### Scenario: Only the Report's own script can run
- **WHEN** the Report is parsed
- **THEN** it has exactly one `script` element, and the policy's `script-src` holds exactly one `'sha256-…'` source, which is the base64 SHA-256 digest of that element's text

#### Scenario: No inline styles or event handlers
- **WHEN** the Report of a Crawl whose Pages contain inline `style` and `onclick` attributes is parsed
- **THEN** no element of the Report has a `style` attribute or an attribute whose name starts with `on`

### Requirement: Report error codes

`report` and `report brief` SHALL report failures as the stderr diagnostics of `010-add-workspace-and-cli-contract`, with nothing on stdout. They define these codes:

| Code | Exit code (class) |
|---|---|
| `unknown_section` | 2 (usage) |
| `notes_dir_not_found` | 4 (not found) |

They also use these codes from other changes:
- `010-add-workspace-and-cli-contract`: `usage_error`, `invalid_value`, `settings_invalid` and `output_not_writable`
- `015-add-crawl-store`: `crawl_not_found`
- `050-add-query-and-segments`: `unknown_segment`

An error about a Report Section id SHALL list the ids in `details.accepted`, and `unknown_section` SHALL also give the closest ids in `details.suggestions`.

#### Scenario: Usage class
- **WHEN** `spider report brief --section title` runs
- **THEN** the exit code is 2, and the error has the code `unknown_section` and a `details.suggestions` that starts with `titles`

#### Scenario: Not-found class
- **WHEN** `spider report --notes does-not-exist` runs
- **THEN** the exit code is 4, and the error has the code `notes_dir_not_found`

### Requirement: Report language and header

The HTML element SHALL have `lang="en"`, and the document SHALL declare `<meta charset="utf-8">`. Every label the tool writes SHALL be in English. The header SHALL show the first Seed in the element `#report-seed`, the Crawl id in `#report-crawl-id` and the Health Score in `#health-score`. The footer SHALL show the tool version and the time the Report was generated, in the element `#generated-at`.

#### Scenario: Language and encoding
- **WHEN** the Report is parsed
- **THEN** the `html` element has `lang="en"` and the document has a `meta` element with `charset="utf-8"`

#### Scenario: Header shows the Seed
- **WHEN** the Report of a Crawl with the Seed `https://example.com/` is parsed
- **THEN** the text of `#report-seed` is `https://example.com/`

### Requirement: Fixed Report Sections

The Report SHALL consist of these parts, in order:
- the header
- the executive summary (`#executive-summary`), present only when there is a notes file for it
- a table of contents (`nav#contents`)
- the Report Sections, in the order below
- the footer

Each Report Section is a `section` element whose `id` is `section-<id>` and whose `h2` heading is its title. Report Section ids are kebab-case. Each Report Section shows the Issues of the Rule categories of `040-add-rules` listed for it; category ids are snake_case:

| # | Id | Title | Rule categories |
|---|---|---|---|
| 1 | `overview` | Overview | none; it shows the top Issues across all categories |
| 2 | `response-codes` | Response Codes | `response_codes` |
| 3 | `indexability` | Indexability | none in v0.1; it shows the Indexability data |
| 4 | `titles` | Titles | `titles` |
| 5 | `meta-descriptions` | Meta Descriptions | `meta_descriptions` |
| 6 | `headings` | Headings | `headings` |
| 7 | `canonicals-and-directives` | Canonicals and Directives | `canonicals`, `directives` |
| 8 | `content` | Content | `content` |
| 9 | `urls` | URLs | `urls` |
| 10 | `images` | Images | `images` |
| 11 | `security` | Security | `security` |
| 12 | `structured-data` | Structured Data | none in v0.1; it shows the structured-data counts |
| 13 | `segments` | Segments | none; it shows the Issues of each Segment |

`segments` SHALL be rendered only when at least one Segment is defined and `--segment` is not given. Every Rule category in the catalogue of `040-add-rules` SHALL map to exactly one of the Report Sections 2–12. Each Issue SHALL appear in the Report Section of its Rule's category as an `article` element whose `data-rule-id` is the rule id. The table of contents SHALL link to every rendered Report Section.

#### Scenario: Report Sections without Segments
- **WHEN** no Segments are defined and the Report is parsed
- **THEN** the ids of the `section` elements whose id starts with `section-` are, in order, `section-overview`, `section-response-codes`, `section-indexability`, `section-titles`, `section-meta-descriptions`, `section-headings`, `section-canonicals-and-directives`, `section-content`, `section-urls`, `section-images`, `section-security` and `section-structured-data`

#### Scenario: Report Sections with Segments
- **WHEN** the Segment `blog` is defined and the Report is parsed
- **THEN** the last `section` element whose id starts with `section-` is `section-segments`

#### Scenario: Table of contents
- **WHEN** no Segments are defined and the Report is parsed
- **THEN** the `href` values of the `a` elements in `nav#contents` are, in order, `#section-overview`, `#section-response-codes`, `#section-indexability`, `#section-titles`, `#section-meta-descriptions`, `#section-headings`, `#section-canonicals-and-directives`, `#section-content`, `#section-urls`, `#section-images`, `#section-security` and `#section-structured-data`

#### Scenario: An Issue appears in its Report Section
- **WHEN** a Crawl has the Issue `title-missing` and the Report is parsed
- **THEN** `section#section-titles` contains an `article` element with `data-rule-id="title-missing"`

#### Scenario: The category mapping
- **WHEN** `spider report brief --list` runs
- **THEN** the `categories` of its entries, in order, are `[]`, `["response_codes"]`, `[]`, `["titles"]`, `["meta_descriptions"]`, `["headings"]`, `["canonicals", "directives"]`, `["content"]`, `["urls"]`, `["images"]`, `["security"]`, `[]` and `[]`

#### Scenario: Every Rule category has a Report Section
- **WHEN** the `category` values of all Rules that `spider rules list --limit 1000` returns are compared with the `categories` of the entries that `spider report brief --list` returns
- **THEN** each of the 10 categories `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images` appears in the `categories` of exactly one entry

### Requirement: Issues in a Report Section

Each `article[data-rule-id]` SHALL contain:
- the Issue Type and the Priority
- the Rule's description, why it matters and how to fix, as escaped plain text
- the thresholds recorded for the Crawl, as a `dl` with each threshold's name in a `dt` and its value in a `dd`
- the Issue's `affected_count`
- a table of its top N Affected URLs, where N is `--top` (1 to 500, default 20), ordered by Unique Inlinks descending and then by URL
- an `a` element linking to the Issue's CSV file, whose text contains the `affected_count`

The table SHALL have the columns URL, Detail, Status Code, Indexability, Unique Inlinks and Segment. The Detail cell shows the Affected URL's `detail` object (`040-add-rules`) as `name: value` pairs separated by `, `. The `titles`, `meta-descriptions` and `headings` Report Sections SHALL add the Title 1, Meta Description 1 and H1-1 column respectively. A Report Section with no Issues SHALL say `No Issues found`. A value that is not measured (`null`) SHALL be shown as `not measured`, never as `0`.

#### Scenario: Guidance of the Rule
- **WHEN** a Crawl has the Issue `title-missing` and the Report is parsed
- **THEN** the text of `article[data-rule-id="title-missing"]` contains the `description`, `why_it_matters` and `how_to_fix` texts that `spider rules show title-missing` prints

#### Scenario: Thresholds
- **WHEN** a Crawl ran with the threshold `max_chars` of `title-too-long` set to 70, and that Issue exists
- **THEN** `article[data-rule-id="title-too-long"]` contains a `dt` with the text `max_chars` followed by a `dd` with the text `70`

#### Scenario: Top 20 by default
- **WHEN** the Issue `title-missing` has 30 Affected URLs and `spider report` runs
- **THEN** the table in `article[data-rule-id="title-missing"]` has 20 body rows

#### Scenario: --top
- **WHEN** the Issue `title-missing` has 30 Affected URLs and `spider report --top 5` runs
- **THEN** the table in `article[data-rule-id="title-missing"]` has 5 body rows

#### Scenario: --top out of range
- **WHEN** `spider report --top 0` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Most-linked Affected URLs first
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/a` (Unique Inlinks 3), `https://example.com/b` (12) and `https://example.com/c` (7)
- **THEN** the URL cells of its table read `https://example.com/b`, `https://example.com/c` and `https://example.com/a`, in that order

#### Scenario: Detail as text
- **WHEN** the Affected URL `https://example.com/a` of `title-too-long` has the `detail` `{"length": 61, "width_px": 536}`
- **THEN** its Detail cell reads `length: 61, width_px: 536`

#### Scenario: Link to the full list
- **WHEN** the Issue `title-missing` has 30 Affected URLs and `spider report` runs
- **THEN** `article[data-rule-id="title-missing"]` contains an `a` element with `href="report-csv/title-missing.csv"` whose text contains `30`

#### Scenario: A Report Section without Issues
- **WHEN** a Crawl has no Issue in the `images` category and the Report is parsed
- **THEN** the text of `section#section-images` contains `No Issues found`

#### Scenario: Not measured is not zero
- **WHEN** the Report of a v0.1 Crawl is parsed
- **THEN** the element `[data-metric="validation_errors"]` in `section#section-structured-data` has the text `not measured`

### Requirement: Key numbers

Each Report Section SHALL show its key numbers as elements with `data-metric="<key>"` and `data-value="<number>"`, where `data-value` is empty for a value that is `null`. Every Report Section from `response-codes` to `structured-data` SHALL have the keys `issues` (the number of its Issues) and `affected_count` (the sum of their `affected_count` values). In `overview`, these keys SHALL equal these members of `spider summary` for the same Crawl and Segment:

| key | summary member |
|---|---|
| `urls` | `totals.urls` |
| `internal_urls` | `totals.internal_urls` |
| `external_urls` | `totals.external_urls` |
| `pages` | `totals.pages` |
| `resources` | `totals.resources` |
| `health_score` | `health_score.score` |
| `issues` | `issues.total` |
| `indexable` | `indexability.indexable` |
| `non_indexable` | `indexability.non_indexable` |

#### Scenario: Overview numbers
- **WHEN** a Crawl has 10 Internal Pages, 2 of which are Affected URLs of *Issue*-type Issues, and the Report is parsed
- **THEN** in `section#section-overview`, `[data-metric="pages"]` has `data-value="10"` and `[data-metric="health_score"]` has `data-value="80"`

#### Scenario: Overview matches summary
- **WHEN** the Report and `spider summary` are produced from the same `completed` Crawl of the local fixture site
- **THEN** each overview key in the table above has a `data-value` equal to the summary member named next to it

#### Scenario: Issue totals of a Report Section
- **WHEN** a Crawl's only Issues in the `titles` category are `title-missing` with `affected_count` 4 and `title-too-long` with 5
- **THEN** in `section#section-titles`, `[data-metric="issues"]` has `data-value="2"` and `[data-metric="affected_count"]` has `data-value="9"`

### Requirement: Health Score display

The element `#health-score` SHALL show the Health Score of the Report's Crawl, or of its Segment under `--segment`, written without a trailing `.0`, or `n/a` when it is `null`. The `segments` Report Section SHALL show a table `#segment-health` with one row per Segment in evaluation order, followed by a `No Segment` row for the Pages in no Segment. Each row gives the name, the number of Pages and the Health Score.

#### Scenario: Health Score in the header
- **WHEN** the Crawl's Health Score is 80 and the Report is parsed
- **THEN** the text of `#health-score` is `80`

#### Scenario: No Internal Pages
- **WHEN** the Crawl has no Internal Pages and the Report is parsed
- **THEN** the text of `#health-score` is `n/a`

#### Scenario: Health Score by Segment
- **WHEN** the Segment `blog` has 4 Internal Pages with 1 Affected URL of an *Issue*-type Issue, the Segment `shop` has 2 Internal Pages with none, and no Page is in no Segment
- **THEN** the rows of `#segment-health` read `blog`, `4`, `75`, then `shop`, `2`, `100`, then `No Segment`, `0`, `n/a`

### Requirement: Charts

Charts SHALL be inline `svg` elements with `role="img"`, a `title` child holding the chart name, and a `desc` child listing the plotted values as `label: value` pairs separated by `; `. The Report SHALL contain these charts:

| Report Section | Chart names |
|---|---|
| `overview` | `Status classes`, `Indexability`, `Content types`, `Crawl Depth`, `Issues by Issue Type and Priority`, `Top Issues` |
| `response-codes` | `Status classes`, `Response time` |
| `indexability` | `Indexability Status` |
| `titles` to `security` | `Affected URLs per Issue` |
| `structured-data` | `Structured data types` |
| `segments` | `Health Score by Segment` |

`Status classes` plots `status_classes.internal`. `Response time` plots `response_time_ms.histogram`. `Affected URLs per Issue` plots the `affected_count` of each Issue in the Report Section, and is left out when the Report Section has no Issues. Any other chart with nothing to plot SHALL be replaced by a `p` element with the text `No data`.

#### Scenario: Overview charts
- **WHEN** the Report of a Crawl of the local fixture site is parsed
- **THEN** the `title` texts of the `svg` elements in `section#section-overview` are `Status classes`, `Indexability`, `Content types`, `Crawl Depth`, `Issues by Issue Type and Priority` and `Top Issues`, in that order

#### Scenario: Response Codes charts
- **WHEN** the Report of a Crawl of the local fixture site is parsed
- **THEN** the `title` texts of the `svg` elements in `section#section-response-codes` are `Status classes` and `Response time`, in that order

#### Scenario: Chart values as text
- **WHEN** a Crawl recorded 8 Internal URLs with 2xx status codes, 2 with 3xx and 1 with 4xx, and the Report is parsed
- **THEN** the `desc` of the `Status classes` chart in `section#section-overview` is `2xx: 8; 3xx: 2; 4xx: 1; 5xx: 0; other: 0; no response: 0; blocked by robots.txt: 0`

#### Scenario: Health Score by Segment chart
- **WHEN** the Segments `blog` and `shop` are defined and the Report is parsed
- **THEN** `section#section-segments` contains an `svg` whose `title` text is `Health Score by Segment`

#### Scenario: Nothing to plot
- **WHEN** no Internal URL of the Crawl returned a response and the Report is parsed
- **THEN** `section#section-response-codes` has no `svg` titled `Response time` and contains a `p` element with the text `No data`

### Requirement: Sortable and filterable tables

Each table of Affected URLs SHALL be an HTML `table` with the class `affected-urls` and a unique `id`, and its rows SHALL be in the HTML, so it can be read without the script. Each header cell SHALL declare `data-sort="text"` or `data-sort="number"`. Each table SHALL have an `input` element with `type="search"` whose `data-filter-for` is the table's `id`. The Report's script SHALL:
- sort a column when its header is activated, alternating ascending and descending, comparing `number` columns numerically, with empty cells last
- hide the rows that do not contain the filter text, compared case-insensitively

#### Scenario: Table structure
- **WHEN** the Report of a Crawl with the Issue `title-missing` is parsed
- **THEN** every `th` of the `table.affected-urls` in `article[data-rule-id="title-missing"]` has a `data-sort` of `text` or `number`, and an `input[type="search"]` has a `data-filter-for` equal to that table's `id`

#### Scenario: Sorting numbers descending
- **WHEN** the Report's table script sorts a `number` column holding `3`, an empty cell, `12` and `7` in descending order
- **THEN** the order is `12`, `7`, `3`, then the empty cell

#### Scenario: Filtering rows
- **WHEN** the Report's table script filters rows holding `https://example.com/blog/a` and `https://example.com/shop/b` with the text `BLOG`
- **THEN** only the row holding `https://example.com/blog/a` stays visible

### Requirement: CSV files with the full lists

The CSV folder SHALL contain:
- `issues.csv`, with one row per Issue and the columns `rule_id,category,issue_type,priority,affected_count,description`
- `<rule-id>.csv` for each Issue, with one row per Affected URL and the columns `url,detail,status_code,indexability,unique_inlinks,segment`, ordered like the Issue's table

The CSV files SHALL follow the CSV policy of `010-add-workspace-and-cli-contract`. Under `--segment`, the rows SHALL be limited to the Segment. Every link from the HTML file to a CSV file SHALL be a relative link into the CSV folder.

#### Scenario: One row per Affected URL
- **WHEN** the Issue `title-missing` has 30 Affected URLs and `spider report` runs
- **THEN** `report-csv/title-missing.csv` has 31 lines, and its first line after the byte-order mark is `url,detail,status_code,indexability,unique_inlinks,segment`

#### Scenario: Issue list
- **WHEN** a Crawl has 3 Issues and `spider report` runs
- **THEN** `report-csv/issues.csv` has 4 lines, and its first line after the byte-order mark is `rule_id,category,issue_type,priority,affected_count,description`

#### Scenario: Relative links
- **WHEN** the Report is parsed
- **THEN** every `a` element whose `href` ends with `.csv` has an `href` that starts with `report-csv/`

#### Scenario: CSV of a Segment Report
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/blog/a`, `https://example.com/blog/b` and `https://example.com/shop/c`, and the Segment `blog` holds the first two
- **AND** `spider report --segment blog` runs
- **THEN** `report-blog-csv/title-missing.csv` has 3 lines

### Requirement: Crawled text is escaped

All text from the Crawl, such as titles, headings, meta descriptions, URLs, `detail` values and header values, and all text from `spider.toml`, such as Segment expressions, SHALL be escaped wherever it appears in the Report: element text, attribute values, SVG labels and the document title. Only the URL cells of Affected URL tables SHALL be links, and only when the URL starts with `http://` or `https://`. Such links SHALL have `rel="noopener noreferrer"`.

#### Scenario: A script in a Page title does not run
- **WHEN** a Page whose title_1 is `<script>alert(1)</script>` is an Affected URL of `title-too-long`, and the Report is parsed
- **THEN** a cell of the table in `article[data-rule-id="title-too-long"]` has the text `<script>alert(1)</script>`, and the document still has exactly one `script` element

#### Scenario: Markup cannot break out of text
- **WHEN** a Page whose meta_description_1 is `"><img src=x onerror=alert(1)>` is an Affected URL of `meta-description-too-long`, and the Report is parsed
- **THEN** the document has no `img` element and no attribute whose name starts with `on`

#### Scenario: Segment expressions are escaped
- **WHEN** `spider.toml` defines `blog = "address contains '<b>x</b>'"` and the Report is parsed
- **THEN** the text of `section#section-segments` contains `address contains '<b>x</b>'`, and `section#section-segments` has no `b` element

#### Scenario: Only web URLs become links
- **WHEN** the `detail` of an Affected URL is `{"canonical_url": "javascript:alert(1)"}` and the Report is parsed
- **THEN** no `a` element has an `href` that starts with `javascript:`

### Requirement: Report Notes files

`--notes <dir>` SHALL read the Report Notes from `<dir>`:
- `summary.md` is rendered as the executive summary in `#executive-summary`.
- `<id>.md`, for each Report Section id, is rendered inside `section#section-<id>` in an element with the class `report-notes`.
- File names are matched case-insensitively.
- A Report Section without a notes file SHALL be rendered without a `report-notes` element.
- Any other visible file SHALL be ignored with the warning `unknown_notes_file`, whose hint names the closest valid file name. Files whose names start with `.` are ignored silently.
- A notes file for a Report Section that is not rendered SHALL be ignored with the warning `notes_not_applicable`.
- A `<dir>` that does not exist SHALL be rejected with the error code `notes_dir_not_found`.

#### Scenario: Executive summary
- **WHEN** `notes/summary.md` holds `Overall the site is healthy.` and `spider report --notes notes` runs
- **THEN** the text of `#executive-summary` contains `Overall the site is healthy.`

#### Scenario: Notes of one Report Section
- **WHEN** `notes/titles.md` holds `Titles are too long on product pages.` and `spider report --notes notes` runs
- **THEN** the text of `section#section-titles .report-notes` contains `Titles are too long on product pages.`

#### Scenario: File names ignore case
- **WHEN** the only notes file is `notes/Titles.MD` and `spider report --notes notes` runs
- **THEN** the receipt's `notes.applied` is `["titles"]`

#### Scenario: Applied and missing notes
- **WHEN** no Segments are defined, `notes` holds only `summary.md` and `titles.md`, and `spider report --notes notes` runs
- **THEN** `notes.applied` is `["summary", "titles"]` and `notes.missing` is `["overview", "response-codes", "indexability", "meta-descriptions", "headings", "canonicals-and-directives", "content", "urls", "images", "security", "structured-data"]`

#### Scenario: Unknown notes file
- **WHEN** `notes` holds `title.md` and `spider report --notes notes` runs
- **THEN** `warnings` holds an entry with code `unknown_notes_file` whose hint contains `titles.md`

#### Scenario: Notes for a Report Section that is not rendered
- **WHEN** no Segments are defined, `notes` holds `segments.md`, and `spider report --notes notes` runs
- **THEN** `warnings` holds an entry with code `notes_not_applicable`

#### Scenario: Hidden files are ignored
- **WHEN** `notes` holds `.DS_Store` and `titles.md`, and `spider report --notes notes` runs
- **THEN** `warnings` is `[]`

#### Scenario: A Report Section without notes
- **WHEN** `notes` holds only `titles.md` and `spider report --notes notes` runs
- **THEN** `section#section-images` contains no element with the class `report-notes`

### Requirement: Report Notes are rendered safely

Report Notes SHALL be rendered as CommonMark with tables:
- Raw HTML in the notes SHALL be shown as literal text.
- Links SHALL become `a` elements only for `http:`, `https:` and `mailto:` targets, with `rel="noopener noreferrer"`. Other targets are shown as text.
- Images SHALL never be loaded; their alt text is shown instead.
- Headings SHALL be demoted so that a level-1 heading becomes `h3` inside a Report Section and inside the executive summary.

Notes in any language SHALL be rendered unchanged.

#### Scenario: A script in notes does not run
- **WHEN** `notes/titles.md` holds `<script>alert(1)</script>` and the Report is parsed
- **THEN** the text of `section#section-titles .report-notes` contains `<script>alert(1)</script>`, and the document has exactly one `script` element

#### Scenario: HTML tags are shown as text
- **WHEN** `notes/titles.md` holds `<b>bold</b>` and the Report is parsed
- **THEN** `section#section-titles .report-notes` has no `b` element, and its text contains `<b>bold</b>`

#### Scenario: javascript links are not links
- **WHEN** `notes/titles.md` holds `[click](javascript:alert(1))` and the Report is parsed
- **THEN** no `a` element has an `href` that starts with `javascript:`, and the notes text contains `click`

#### Scenario: Web links keep working
- **WHEN** `notes/titles.md` holds `[docs](https://example.com/docs)` and the Report is parsed
- **THEN** `section#section-titles .report-notes` has an `a` element with `href="https://example.com/docs"` and `rel="noopener noreferrer"`

#### Scenario: Remote images are not loaded
- **WHEN** `notes/titles.md` holds `![chart](https://evil.example/c.png)` and the Report is parsed
- **THEN** the document has no `img` element

#### Scenario: Headings are demoted
- **WHEN** `notes/titles.md` holds `# Findings` and the Report is parsed
- **THEN** `section#section-titles .report-notes` has an `h3` element with the text `Findings` and no `h1` or `h2` element

#### Scenario: Tables in notes
- **WHEN** `notes/titles.md` holds a Markdown table with the header `| Page | Fix |` and one row `| /a | Shorten |`, and the Report is parsed
- **THEN** `section#section-titles .report-notes` has a `table` element whose first body row has the cells `/a` and `Shorten`

#### Scenario: Notes in any language
- **WHEN** `notes/titles.md` holds `Заголовки слишком длинные. 見出しが長すぎます。` in UTF-8 and the Report is parsed
- **THEN** the text of `section#section-titles .report-notes` contains `Заголовки слишком длинные. 見出しが長すぎます。`

### Requirement: Report Notes file encodings

A notes file SHALL be read as UTF-8, with or without a byte-order mark, or as UTF-16 when it starts with a UTF-16 byte-order mark. That is what Windows PowerShell 5.1's `Out-File` writes. A file that is not valid UTF-8 and has no UTF-16 byte-order mark SHALL be rendered with replacement characters, with the warning `notes_encoding` naming the file.

#### Scenario: UTF-8 with a byte-order mark
- **WHEN** `notes/titles.md` holds a UTF-8 byte-order mark followed by `Hello`, and the Report is parsed
- **THEN** the text of `section#section-titles .report-notes` is `Hello`, with no U+FEFF character

#### Scenario: UTF-16 notes written on Windows
- **WHEN** `notes/titles.md` holds the UTF-16 LE encoding, with a byte-order mark, of `Заголовки`, as Windows PowerShell 5.1 `Out-File` writes it, and the Report is parsed
- **THEN** the text of `section#section-titles .report-notes` contains `Заголовки`

#### Scenario: Invalid bytes
- **WHEN** `notes/titles.md` holds the bytes `Hello \xff world`, and `spider report --notes notes` runs
- **THEN** `warnings` holds an entry with code `notes_encoding` whose message contains `titles.md`

### Requirement: Section Crawls and incomplete Crawls are labelled

For a Section Crawl, the header SHALL show the text `Section Crawl` in `#section-crawl-label`, the Crawl Depth chart SHALL be titled `Crawl Depth (partial)`, and the Unique Inlinks header cell of every Affected URL table SHALL read `Unique Inlinks (partial)`. For a Crawl whose Crawl State is not `completed`, the header SHALL show a notice `#crawl-state-notice` whose text contains `Crawl State:` followed by the state. A `completed` whole-site Crawl SHALL have neither element.

#### Scenario: Section Crawl label
- **WHEN** the Report of a Section Crawl is parsed
- **THEN** the text of `#section-crawl-label` is `Section Crawl`

#### Scenario: Partial link metrics
- **WHEN** the Report of a Section Crawl with the Issue `title-missing` is parsed
- **THEN** the overview has an `svg` whose `title` text is `Crawl Depth (partial)`, and the table in `article[data-rule-id="title-missing"]` has a `th` with the text `Unique Inlinks (partial)`

#### Scenario: A running Crawl
- **WHEN** the Report of a Crawl in the Crawl State `running` is parsed
- **THEN** the text of `#crawl-state-notice` contains `Crawl State: running`

#### Scenario: A stopped Crawl
- **WHEN** the Report of a Crawl in the Crawl State `stopped` is parsed
- **THEN** the text of `#crawl-state-notice` contains `Crawl State: stopped`

#### Scenario: Completed whole-site Crawl
- **WHEN** the Report of a `completed` whole-site Crawl is parsed
- **THEN** the document has no `#section-crawl-label` and no `#crawl-state-notice` element

### Requirement: Segment Report

`spider report --segment <name>` SHALL build every Report Section from that Segment's Pages, using the Segment rules of `050-add-query-and-segments`. It SHALL show the Segment name in `#report-segment` and leave out the `segments` Report Section. An unknown name SHALL be rejected with 050's `unknown_segment` (exit code 2).

#### Scenario: Segment name in the header
- **WHEN** the Segment `blog` is defined and `spider report --segment blog` runs
- **THEN** the text of `#report-segment` is `blog`

#### Scenario: Health Score of the Segment
- **WHEN** `spider summary --segment blog` returns a `health_score.score` of 75 and `spider report --segment blog` runs
- **THEN** the text of `#health-score` is `75`

#### Scenario: Unknown Segment
- **WHEN** `spider report --segment blgo` runs
- **THEN** the exit code is 2, and the error has the code `unknown_segment`

### Requirement: Opening the Report

`spider report --open` SHALL hand the HTML file to the operating system's default browser without waiting for the browser to close:
- on Windows, through the file's default association
- on macOS, with `open`
- on Linux, with `xdg-open`, but only when a desktop session is present (`DISPLAY` or `WAYLAND_DISPLAY` is set)

When the Report cannot be handed over, it SHALL still be written, the command SHALL exit with code 0, `opened` SHALL be `false`, and `warnings` SHALL hold an entry with code `open_failed`. Without `--open`, no browser SHALL be started.

#### Scenario: Windows
- **WHEN** on Windows, `spider report --open` runs
- **THEN** the operating system is asked once to open the receipt's `path` with its default application, and the receipt has `"opened": true`

#### Scenario: macOS
- **WHEN** on macOS, `spider report --open` runs
- **THEN** a process `open <path>` is started without being waited for, and the receipt has `"opened": true`

#### Scenario: Linux desktop
- **WHEN** on Linux with `DISPLAY=:0`, `spider report --open` runs
- **THEN** a process `xdg-open <path>` is started without being waited for

#### Scenario: Linux without a desktop
- **WHEN** on Linux, with neither `DISPLAY` nor `WAYLAND_DISPLAY` set, `spider report --open` runs
- **THEN** no process is started, the exit code is 0, and `warnings` holds an entry with code `open_failed`

#### Scenario: No opener installed
- **WHEN** on Linux with `DISPLAY=:0` and no `xdg-open` on the `PATH`, `spider report --open` runs
- **THEN** the exit code is 0, and the receipt has `"opened": false`

### Requirement: No settings or secrets in the Report

The Report and its CSV files SHALL NOT include the command line or the config recorded for the Crawl, or any value from them, such as credentials, custom header values or proxy settings.

#### Scenario: Credentials are not copied
- **WHEN** the Crawl was recorded with the basic-auth password `s3cr3t-pass` and the custom header `Authorization: Bearer tok123`, and `spider report` runs
- **THEN** neither `s3cr3t-pass` nor `tok123` occurs in the HTML file or in any file of the CSV folder

### Requirement: Repeatable output

Two runs of `spider report` for the same Crawl, Segment definitions, notes and flags SHALL produce CSV files with identical bytes, and HTML files that differ only in the text of `#generated-at`.

#### Scenario: Two runs
- **WHEN** `spider report --dest a` and `spider report --dest b` run one after the other against the same `completed` Crawl
- **THEN** `a/report.html` and `b/report.html` are identical once the text of `#generated-at` is removed from both, and `a/report-csv` and `b/report-csv` hold byte-identical files

### Requirement: Report size is bounded

The HTML file's size SHALL depend on the number of Issues and on `--top`, not on the number of Pages.

#### Scenario: A large Crawl
- **WHEN** a Crawl has 100,000 Pages and 20 Issues, each with `affected_count` 100,000, and `spider report` runs with the default `--top`
- **THEN** the HTML file is at most 5,000,000 bytes

### Requirement: Section Brief

`spider report brief --section <id>` SHALL return one JSON object, the Section Brief, with exactly these members:
- `brief_version`: `1`
- `section`: `{id, title, applicable, notes_file}`, where `notes_file` is `<id>.md`
- `crawl`: the `crawl` member of `spider summary`
- `segment`
- `counts`: the Report Section's key numbers, with the same keys and values as its `data-metric` elements
- `issues`: the Report Section's Issues in Report order, each `{rule_id, category, issue_type, priority, affected_count, description, how_to_fix, thresholds, sample_affected_urls}`, where `sample_affected_urls` holds up to 5 `{url, detail}` taken from the top of the Issue's table
- `rules_without_issues`: the ids of the Report Section's Rules that are enabled in the Crawl's `rules` table but have no Affected URL
- `partial_link_metrics`: `true` for a Section Crawl
- `truncated`, `omitted_issues` and `max_bytes`: see the size budget requirement

`--segment` SHALL limit the brief to one Segment, as in the Report. A Report Section that would not be rendered SHALL still get a brief, with `section.applicable` `false`, empty `counts` and empty `issues`. The `overview` brief holds the Crawl's top 10 Issues across all Report Sections.

#### Scenario: Members
- **WHEN** `spider report brief --section titles` runs
- **THEN** the output's keys are exactly `brief_version`, `section`, `crawl`, `segment`, `counts`, `issues`, `rules_without_issues`, `partial_link_metrics`, `truncated`, `omitted_issues` and `max_bytes`

#### Scenario: The brief's section member
- **WHEN** `spider report brief --section titles` runs
- **THEN** `section` is `{"id": "titles", "title": "Titles", "applicable": true, "notes_file": "titles.md"}`

#### Scenario: Samples come from the top of the table
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/p1` to `https://example.com/p7`, whose Unique Inlinks equal their numbers
- **AND** `spider report brief --section titles` runs
- **THEN** the `url` values of that Issue's `sample_affected_urls` are `https://example.com/p7`, `https://example.com/p6`, `https://example.com/p5`, `https://example.com/p4` and `https://example.com/p3`

#### Scenario: Thresholds in the brief
- **WHEN** a Crawl ran with the threshold `max_chars` of `title-too-long` set to 70, and that Issue exists
- **AND** `spider report brief --section titles` runs
- **THEN** the `thresholds` of the `title-too-long` item is `{"max_chars": 70, "max_pixels": 561}`

#### Scenario: Rules without Issues
- **WHEN** `title-missing` is the Crawl's only Issue in the `titles` category
- **AND** `spider report brief --section titles` runs
- **THEN** `rules_without_issues` contains `title-too-long` and does not contain `title-missing`

#### Scenario: Counts equal the Report
- **WHEN** the Report and `spider report brief --section titles` are produced from the same `completed` Crawl
- **THEN** the brief's `counts` equals the `data-metric` keys and `data-value` numbers of `section#section-titles`

#### Scenario: Crawl member equals the summary
- **WHEN** `spider report brief --section overview` and `spider summary` run against the same `completed` Crawl
- **THEN** the brief's `crawl` equals the summary's `crawl`

#### Scenario: A brief for one Segment
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/blog/a`, `https://example.com/blog/b` and `https://example.com/shop/c`, and the Segment `blog` holds the first two
- **AND** `spider report brief --section titles --segment blog` runs
- **THEN** `segment` is `blog`, and the `title-missing` item has `"affected_count": 2`

#### Scenario: A Report Section that is not rendered
- **WHEN** no Segments are defined and `spider report brief --section segments` runs
- **THEN** the exit code is 0, and the output has `"applicable": false` in `section`, `"counts": {}` and `"issues": []`

#### Scenario: Section Crawl brief
- **WHEN** `spider report brief --section overview` runs against a Section Crawl
- **THEN** `partial_link_metrics` is `true`

### Requirement: Section Brief size budget

The Section Brief, serialised as compact UTF-8 JSON, SHALL be at most `max_bytes` bytes. `max_bytes` is set by `--max-bytes`, which accepts 8,192 to 1,048,576, and defaults to 16,384. When the full brief is larger, the tool SHALL apply these steps in order and stop as soon as the brief fits:
1. Reduce every Issue's `sample_affected_urls`, one entry at a time, down to 1.
2. Cut every string longer than 300 characters to 300 characters ending with `…`.
3. Remove `how_to_fix`, starting from the last Issue.
4. Remove Issues from the end, adding their rule ids to `omitted_issues`.

`truncated` SHALL be `true` exactly when a step was applied.

#### Scenario: A small brief is complete
- **WHEN** `spider report brief --section titles` runs against a Crawl with 2 Issues in the `titles` category and short URLs
- **THEN** `truncated` is `false` and `omitted_issues` is `[]`

#### Scenario: The budget holds for long URLs
- **WHEN** the `titles` Report Section has 6 Issues, each with 5 or more Affected URLs of 2,000 characters
- **AND** `spider report brief --section titles` runs
- **THEN** stdout is at most 16,384 bytes, and `truncated` is `true`

#### Scenario: Samples are reduced first
- **WHEN** the full `titles` brief is 20,000 bytes only because of its samples, and cutting every Issue to 1 sample brings it under 16,384 bytes
- **AND** `spider report brief --section titles` runs
- **THEN** `omitted_issues` is `[]`, every Issue still has `how_to_fix`, and every Issue has exactly 1 sample

#### Scenario: A smaller budget
- **WHEN** the same 6-Issue brief is requested with `--max-bytes 8192`
- **THEN** stdout is at most 8,192 bytes

#### Scenario: Budget out of range
- **WHEN** `spider report brief --section titles --max-bytes 100` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: Choosing a Report Section

`spider report brief --list` SHALL return `{sections: [...]}` with one entry per Report Section id, in Report order: `{id, title, applicable, categories, issues, affected_count, notes_file}`. `categories` lists the snake_case Rule category ids of `040-add-rules` that the Report Section shows. The accepted values of `--section` that `spider commands --format json` lists SHALL be exactly the thirteen Report Section ids.
- `report brief` without `--section` or `--list`, and `report brief` with both, SHALL fail with the `usage_error` of `010-add-workspace-and-cli-contract`, whose `details.accepted` lists the Report Section ids.
- An unknown id SHALL fail with `unknown_section`.

#### Scenario: Listed ids
- **WHEN** `spider report brief --list` runs
- **THEN** the `id` values of `sections` are `overview`, `response-codes`, `indexability`, `titles`, `meta-descriptions`, `headings`, `canonicals-and-directives`, `content`, `urls`, `images`, `security`, `structured-data` and `segments`, in that order

#### Scenario: Applicability without Segments
- **WHEN** no Segments are defined and `spider report brief --list` runs
- **THEN** the `segments` entry has `"applicable": false`, and every other entry has `"applicable": true`

#### Scenario: Issue counts per Report Section
- **WHEN** a Crawl's only Issues in the `titles` category are `title-missing` with `affected_count` 4 and `title-too-long` with 5
- **AND** `spider report brief --list` runs
- **THEN** the `titles` entry has `"issues": 2` and `"affected_count": 9`

#### Scenario: Accepted values for agents
- **WHEN** `spider commands --format json` runs
- **THEN** the accepted values of `report brief --section` are exactly the thirteen Report Section ids

#### Scenario: No Report Section given
- **WHEN** `spider report brief` runs without `--section` or `--list`
- **THEN** the exit code is 2, and the error has the code `usage_error` and a `details.accepted` that starts with `overview`

#### Scenario: Both --section and --list
- **WHEN** `spider report brief --section titles --list` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

### Requirement: Report of a detached Crawl, end to end

On Windows, macOS and Linux, a Crawl started with `crawl --detach` (`060-add-crawl-control`) and followed with `status` until its Crawl State is `completed` SHALL give, through `issues` and `report` run as separate processes, a Report of that Crawl.

#### Scenario: Detached Crawl to Report
- **WHEN** on each CI operating system, as real subprocesses, `spider crawl <fixture site>/ --detach` runs, `spider status` is polled until it reports the Crawl State `completed`, and then `spider issues` and `spider report` run, against a fixture site that has a Page without a `<title>`
- **THEN** every command exits with code 0, and the HTML file named by the receipt's `path` contains an `article` element with `data-rule-id="title-missing"`
