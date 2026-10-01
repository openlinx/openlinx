Each implementation task below is **one red → green slice** for one scenario, or for a trivial pair. Scenarios are named `Requirement › Scenario` from `specs/reporting/spec.md`.
1. Write the test at the named seam (docs/testing.md), with the literal expected values from the spec, and watch it fail for the right reason.
2. Write only enough code to pass it.
3. Run ruff, the strict type checker and pytest with coverage.
4. Make one commit whose message names the scenario.

Crawl stores come from 050's `crawl_store` factory, which writes documented tables only, or from real Crawls of the local fixture site. The only boundary doubles are the OS process-spawn call (for `--open`) and the injectable clock.

Every group ends with a docs task and a review task.

## 1. Report Section registry and `report brief --list` (seams 1: CLI, 2: Services)

- [ ] 1.1 Drive `Choosing a Report Section › Listed ids` (CLI): the Report Section registry (kebab-case id, title, order) and `spider report brief --list`. Verify: red → green; one commit.
- [ ] 1.2 Drive `Fixed Report Sections › The category mapping` (CLI): the registry's snake_case 040 category ids. Verify: red → green; one commit.
- [ ] 1.3 Drive `Fixed Report Sections › Every Rule category has a Report Section` (CLI, against 040's `spider rules list`). Verify: red → green; one commit.
- [ ] 1.4 Drive `Choosing a Report Section › Applicability without Segments` (Services), using 050's Segment resolution. Verify: red → green; one commit.
- [ ] 1.5 Drive `Choosing a Report Section › Issue counts per Report Section` (Services): `issues` and `affected_count` per entry. Verify: red → green; one commit.
- [ ] 1.6 Drive `Choosing a Report Section › Accepted values for agents` (CLI): the `--section` Choice subclass. Verify: red → green; one commit.
- [ ] 1.7 Drive `Report error codes › Usage class` (CLI): `unknown_section` with `details.suggestions` and `details.accepted`. Verify: red → green; one commit.
- [ ] 1.8 Drive the pair `Choosing a Report Section › No Report Section given` and `› Both --section and --list` (CLI): 010's `usage_error` with `details.accepted`. Verify: red → green; one commit.
- [ ] 1.9 Docs: start `docs/report.md` with the Report Section table (ids, titles, Rule categories, charts) and `report brief --list`. Verify: all thirteen ids and the category mapping appear.
- [ ] 1.10 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green. Verify: findings resolved or recorded; one commit.

## 2. Section Briefs (seams 1: CLI, 2: Services)

- [ ] 2.1 Drive `Section Brief › Members` (CLI): the brief skeleton built from the registry. Verify: red → green; one commit.
- [ ] 2.2 Drive `Section Brief › The brief's section member` (CLI). Verify: red → green; one commit.
- [ ] 2.3 Drive `Section Brief › Crawl member equals the summary` (Services), reusing 050's `SummaryModel`. Verify: red → green; one commit.
- [ ] 2.4 Drive `Section Brief › Samples come from the top of the table` (Services), in 050's Affected URL order. Verify: red → green; one commit.
- [ ] 2.5 Drive `Section Brief › Thresholds in the brief` (Services), from the Crawl's `rules` table. Verify: red → green; one commit.
- [ ] 2.6 Drive `Section Brief › Rules without Issues` (Services), from the `enabled` column of the Crawl's `rules` table. Verify: red → green; one commit.
- [ ] 2.7 Drive `Section Brief › A brief for one Segment` (Services). Verify: red → green; one commit.
- [ ] 2.8 Drive `Section Brief › A Report Section that is not rendered` (CLI). Verify: red → green; one commit.
- [ ] 2.9 Drive `Section Brief › Section Crawl brief` (Services). Verify: red → green; one commit.
- [ ] 2.10 Drive `Section Brief size budget › A small brief is complete` (CLI). Verify: red → green; one commit.
- [ ] 2.11 Drive `Section Brief size budget › Budget out of range` (CLI). Verify: red → green; one commit.
- [ ] 2.12 Drive `Section Brief size budget › The budget holds for long URLs` (CLI): the four-step reduction loop. Verify: red → green; one commit.
- [ ] 2.13 Drive `Section Brief size budget › Samples are reduced first` (CLI). Verify: red → green; one commit.
- [ ] 2.14 Drive `Section Brief size budget › A smaller budget` (CLI). Verify: red → green; one commit.
- [ ] 2.15 Docs: write `docs/contracts/section-brief.md`: every member, the budget and its reduction steps, an example for `titles`, and how an agent treats `applicable: false`. Verify: the example parses and fits 16,384 bytes.
- [ ] 2.16 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 3. The HTML file: destination, receipt and safety (seams 1: CLI, 7: Report)

- [ ] 3.1 Drive `Report files › Default location` (CLI): the Report Service, a minimal Jinja2 template with autoescaping, and the default destination `.spider/reports/<crawl id>/`. Verify: red → green; one commit.
- [ ] 3.2 Drive `Report files › Default CSV folder` (CLI). Verify: red → green; one commit.
- [ ] 3.3 Drive `Report receipt › Receipt without notes` (CLI). Verify: red → green; one commit.
- [ ] 3.4 Drive `Report receipt › -o redirects the receipt` (CLI), relying on 050's `-o`. Verify: red → green; one commit.
- [ ] 3.5 Drive `Report files › --dest names the folder` (CLI). Verify: red → green; one commit.
- [ ] 3.6 Drive `Report language and header › Language and encoding` (Report). Verify: red → green; one commit.
- [ ] 3.7 Drive `Report language and header › Header shows the Seed` (Report). Verify: red → green; one commit.
- [ ] 3.8 Drive `Fixed Report Sections › Report Sections without Segments` (Report). Verify: red → green; one commit.
- [ ] 3.9 Drive `Fixed Report Sections › Report Sections with Segments` (Report). Verify: red → green; one commit.
- [ ] 3.10 Drive `Fixed Report Sections › Table of contents` (Report). Verify: red → green; one commit.
- [ ] 3.11 Drive `Self-contained offline Report › Nothing is loaded from elsewhere` (Report, on a fixture-site Crawl, 3+6). Verify: red → green; one commit.
- [ ] 3.12 Drive `Self-contained offline Report › Content-Security-Policy` (Report). Verify: red → green; one commit.
- [ ] 3.13 Drive `Self-contained offline Report › Only the Report's own script can run` (Report): the single inline script, and its hash in the CSP. Verify: red → green; one commit.
- [ ] 3.14 Drive `Self-contained offline Report › No inline styles or event handlers` (Report). Verify: red → green; one commit.
- [ ] 3.15 Drive `Health Score display › Health Score in the header` (Report). Verify: red → green; one commit.
- [ ] 3.16 Drive `Health Score display › No Internal Pages` (Report). Verify: red → green; one commit.
- [ ] 3.17 Drive `Key numbers › Overview numbers` (Report): overview key numbers from `SummaryModel`. Verify: red → green; one commit.
- [ ] 3.18 Drive `Key numbers › Overview matches summary` (Report, on a fixture-site Crawl, 3+6). Verify: red → green; one commit.
- [ ] 3.19 Drive `No settings or secrets in the Report › Credentials are not copied` (Report), with a store whose recorded config holds credentials. Verify: red → green; one commit.
- [ ] 3.20 Drive `Repeatable output › Two runs` (Report, with the injectable clock). Verify: red → green; one commit.
- [ ] 3.21 Docs: in `docs/report.md`, describe the Report's layout, `--dest` and the default folder (which `crawls rm` deletes), the receipt and `-o`, and the security model (escaping, CSP, no settings copied). Verify: every member of the receipt is documented.
- [ ] 3.22 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 4. Report Section content (seams 7: Report, 1: CLI)

- [ ] 4.1 Drive `Fixed Report Sections › An Issue appears in its Report Section` (Report): the Issue `article`, placed by the category mapping. Verify: red → green; one commit.
- [ ] 4.2 Drive `Issues in a Report Section › Guidance of the Rule` (Report): guidance as escaped paragraphs. Verify: red → green; one commit.
- [ ] 4.3 Drive `Issues in a Report Section › Thresholds` (Report). Verify: red → green; one commit.
- [ ] 4.4 Drive `Issues in a Report Section › Top 20 by default` (Report): the Affected URL table. Verify: red → green; one commit.
- [ ] 4.5 Drive `Issues in a Report Section › --top` (Report). Verify: red → green; one commit.
- [ ] 4.6 Drive `Issues in a Report Section › --top out of range` (CLI). Verify: red → green; one commit.
- [ ] 4.7 Drive `Issues in a Report Section › Most-linked Affected URLs first` (Report). Verify: red → green; one commit.
- [ ] 4.8 Drive `Issues in a Report Section › Detail as text` (Report). Verify: red → green; one commit.
- [ ] 4.9 Drive `Issues in a Report Section › Link to the full list` (Report). Verify: red → green; one commit.
- [ ] 4.10 Drive `Issues in a Report Section › A Report Section without Issues` (Report). Verify: red → green; one commit.
- [ ] 4.11 Drive `Issues in a Report Section › Not measured is not zero` (Report). Verify: red → green; one commit.
- [ ] 4.12 Drive `Key numbers › Issue totals of a Report Section` (Report): `issues` and `affected_count` for Report Sections 2–12. Verify: red → green; one commit.
- [ ] 4.13 Drive `Crawled text is escaped › A script in a Page title does not run` (Report): the extra Title 1 column of the `titles` Report Section. Verify: red → green; one commit.
- [ ] 4.14 Drive `Crawled text is escaped › Markup cannot break out of text` (Report). Verify: red → green; one commit.
- [ ] 4.15 Drive `Crawled text is escaped › Only web URLs become links` (Report). Verify: red → green; one commit.
- [ ] 4.16 Drive `Section Crawls and incomplete Crawls are labelled › Section Crawl label` (Report). Verify: red → green; one commit.
- [ ] 4.17 Drive `Section Crawls and incomplete Crawls are labelled › Partial link metrics` (Report). Verify: red → green; one commit.
- [ ] 4.18 Drive the pair `Section Crawls and incomplete Crawls are labelled › A running Crawl` and `› A stopped Crawl` (Report). Verify: red → green; one commit.
- [ ] 4.19 Drive `Section Crawls and incomplete Crawls are labelled › Completed whole-site Crawl` (Report). Verify: red → green; one commit.
- [ ] 4.20 Drive `Report size is bounded › A large Crawl` (Report, a synthetic store of 100,000 Pages from the factory, marked slow). Verify: red → green; one commit.
- [ ] 4.21 Docs: in `docs/report.md`, describe what each Report Section shows, the top-N rule, "not measured", and the Section Crawl and Crawl State labels. Verify: every Report Section id has a paragraph.
- [ ] 4.22 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 5. Charts and interactive tables (seams 7: Report, 9: Report script)

- [ ] 5.1 Drive `Charts › Overview charts` (Report): the SVG builder (bar, horizontal bar, stacked bar, 3×3 matrix), with presentation attributes only and deterministic ids. Verify: red → green; one commit.
- [ ] 5.2 Drive `Charts › Chart values as text` (Report): `title` and `desc`. Verify: red → green; one commit.
- [ ] 5.3 Drive `Charts › Response Codes charts` (Report): the histogram. Verify: red → green; one commit.
- [ ] 5.4 Drive `Charts › Nothing to plot` (Report): the `No data` fallback. Verify: red → green; one commit.
- [ ] 5.5 Drive `Health Score display › Health Score by Segment` (Report): the `#segment-health` table. Verify: red → green; one commit.
- [ ] 5.6 Drive `Charts › Health Score by Segment chart` (Report). Verify: red → green; one commit.
- [ ] 5.7 Drive `Crawled text is escaped › Segment expressions are escaped` (Report). Verify: red → green; one commit.
- [ ] 5.8 Drive `Sortable and filterable tables › Table structure` (Report): the `data-sort` types, table ids and search inputs. Verify: red → green; one commit.
- [ ] 5.9 Drive `Sortable and filterable tables › Sorting numbers descending` (seam 9): the pure functions of `table.js` under `node --test`, a pytest wrapper that skips without Node locally and fails in CI, and the check that the CI jobs (Node set up by 000) run it. Verify: red → green on all three CI OSes; one commit.
- [ ] 5.10 Drive `Sortable and filterable tables › Filtering rows` (seam 9). Verify: red → green; one commit.
- [ ] 5.11 Docs: in `docs/report.md`, list the charts and explain how tables sort and filter. In `CONTRIBUTING.md`, note that the seam 9 tests need Node. Verify: every chart name in the spec is documented.
- [ ] 5.12 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 6. CSV files with the full lists (seams 1: CLI, 7: Report)

- [ ] 6.1 Drive `CSV files with the full lists › One row per Affected URL` (CLI): 050's CSV serialiser, in its Affected URL order. Verify: red → green; one commit.
- [ ] 6.2 Drive `CSV files with the full lists › Issue list` (CLI). Verify: red → green; one commit.
- [ ] 6.3 Drive `CSV files with the full lists › Relative links` (Report). Verify: red → green; one commit.
- [ ] 6.4 Drive `CSV files with the full lists › CSV of a Segment Report` (CLI). Verify: red → green; one commit.
- [ ] 6.5 Docs: in `docs/report.md`, describe the CSV folder (file names and columns), with a pointer to 050's CSV policy for Excel on Windows. Verify: both CSV headers from the spec are quoted.
- [ ] 6.6 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 7. Report Notes (seams 7: Report, 1: CLI)

- [ ] 7.1 Drive `Report Notes files › Executive summary` (Report): markdown-it-py with `html=False`. Verify: red → green; one commit.
- [ ] 7.2 Drive `Report Notes files › Notes of one Report Section` (Report). Verify: red → green; one commit.
- [ ] 7.3 Drive `Report Notes files › A Report Section without notes` (Report). Verify: red → green; one commit.
- [ ] 7.4 Drive `Report Notes files › File names ignore case` (CLI). Verify: red → green; one commit.
- [ ] 7.5 Drive `Report Notes files › Applied and missing notes` (CLI). Verify: red → green; one commit.
- [ ] 7.6 Drive `Report Notes files › Unknown notes file` (CLI). Verify: red → green; one commit.
- [ ] 7.7 Drive `Report Notes files › Notes for a Report Section that is not rendered` (CLI). Verify: red → green; one commit.
- [ ] 7.8 Drive `Report Notes files › Hidden files are ignored` (CLI). Verify: red → green; one commit.
- [ ] 7.9 Drive `Report error codes › Not-found class` (CLI): `notes_dir_not_found`. Verify: red → green; one commit.
- [ ] 7.10 Drive `Report Notes are rendered safely › A script in notes does not run` (Report). Verify: red → green; one commit.
- [ ] 7.11 Drive `Report Notes are rendered safely › HTML tags are shown as text` (Report). Verify: red → green; one commit.
- [ ] 7.12 Drive `Report Notes are rendered safely › javascript links are not links` (Report): `validateLink`. Verify: red → green; one commit.
- [ ] 7.13 Drive `Report Notes are rendered safely › Web links keep working` (Report): `rel` on links. Verify: red → green; one commit.
- [ ] 7.14 Drive `Report Notes are rendered safely › Remote images are not loaded` (Report). Verify: red → green; one commit.
- [ ] 7.15 Drive `Report Notes are rendered safely › Headings are demoted` (Report). Verify: red → green; one commit.
- [ ] 7.16 Drive `Report Notes are rendered safely › Tables in notes` (Report). Verify: red → green; one commit.
- [ ] 7.17 Drive `Report Notes are rendered safely › Notes in any language` (Report). Verify: red → green; one commit.
- [ ] 7.18 Drive `Report Notes file encodings › UTF-8 with a byte-order mark` (Report). Verify: red → green; one commit.
- [ ] 7.19 Drive `Report Notes file encodings › UTF-16 notes written on Windows` (Report): BOM sniffing. Verify: red → green; one commit.
- [ ] 7.20 Drive `Report Notes file encodings › Invalid bytes` (CLI). Verify: red → green; one commit.
- [ ] 7.21 Docs: write `docs/contracts/report-notes.md`, the file contract that 080's Skill follows: file names, encodings, supported Markdown, what is shown as text, heading levels, and the warnings. Verify: every warning code in the spec is listed.
- [ ] 7.22 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 8. `report` options and platform behaviour (seams 1: CLI, 7: Report)

- [ ] 8.1 Drive `Report files › Location of a Segment Report` (CLI). Verify: red → green; one commit.
- [ ] 8.2 Drive `Segment Report › Segment name in the header` (Report). Verify: red → green; one commit.
- [ ] 8.3 Drive `Segment Report › Health Score of the Segment` (Report). Verify: red → green; one commit.
- [ ] 8.4 Drive `Segment Report › Unknown Segment` (CLI). Verify: red → green; one commit.
- [ ] 8.5 Drive `Report files › Re-running removes CSV files that no longer apply` (CLI): build in a temporary folder, swap the CSV folder, then replace the HTML last, with rollback. Verify: red → green; one commit.
- [ ] 8.6 Drive `Report files › Windows folder with spaces and non-ASCII characters` (CLI, real subprocess, Windows-only). Verify: red → green on the Windows CI job; one commit.
- [ ] 8.7 Drive `Report files › A locked CSV file on Windows leaves the previous Report intact` (CLI, real subprocess, Windows-only), including the short rename retry and `output_not_writable`. Verify: red → green on the Windows CI job; one commit.
- [ ] 8.8 Drive `Opening the Report › Windows` (CLI, with the OS spawn call as the boundary double). Verify: red → green; one commit.
- [ ] 8.9 Drive `Opening the Report › macOS` (CLI, the same double). Verify: red → green; one commit.
- [ ] 8.10 Drive `Opening the Report › Linux desktop` (CLI, the same double). Verify: red → green; one commit.
- [ ] 8.11 Drive `Opening the Report › Linux without a desktop` (CLI). Verify: red → green; one commit.
- [ ] 8.12 Drive `Opening the Report › No opener installed` (CLI). Verify: red → green; one commit.
- [ ] 8.13 Docs: in `docs/report.md`, document `--segment`, `--dest`, `--top` and `--open` (and why nothing opens on headless Linux), and what happens when a CSV file is open in Excel. Verify: every flag of `report` is documented.
- [ ] 8.14 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green. Verify: suite green; one commit.

## 9. End to end (seams 7: Report, 3+6, 1: CLI with real processes)

- [ ] 9.1 Drive `Section Brief › Counts equal the Report` (Report), comparing the brief with the HTML of the same Crawl for `titles`. Verify: red → green; one commit.
- [ ] 9.2 Drive `Report of a detached Crawl, end to end › Detached Crawl to Report` (CLI, real subprocesses against the fixture site, marked `e2e`; needs 060's `--detach` and `status`). Add the test to the CI jobs on Windows, macOS and Linux. Verify: red → green on all three CI OSes; one commit.
- [ ] 9.3 Docs: finish `docs/report.md` with the agent workflow (list, briefs, notes, report), and link the two contract documents from the README. Verify: links resolve.
- [ ] 9.4 Review: run the code-review skill on group 9's commits and on the change as a whole against the spec, then refactor with the whole suite green. Verify: suite green on Windows, macOS and Linux; one commit.
