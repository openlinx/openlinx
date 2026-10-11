> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Every task is one red → green slice and one commit whose message names its scenario:
1. Write the failing test at the named seam (docs/testing.md) and watch it fail for the right reason.
2. Write only enough code to make it pass.
3. Run the full suite.

`<home>` and `<cwd>` are temporary folders. On Windows, `<home>` is set through `USERPROFILE`. The Skill's content is read from the folder that `spider skill install` wrote.

## 1. Install and generation basics

- [ ] 1.1 Drive "Installed Skill folder" (CLI seam). Add:
  - the `skill` Command group with `install --target claude`
  - the generator module
  - the constants module: placeholder names, `OWNER/REPO`, the Hand-off threshold of 5,000, and the install one-liners
  - six minimal templates
- [ ] 1.2 Drive "Default installs for both targets" (CLI seam).
- [ ] 1.3 Drive "Fresh install result" (CLI seam).
- [ ] 1.4 Drive "Stamp equals the CLI version" (CLI seam).
- [ ] 1.5 Drive "Stamp lies within the first 4 KiB" (CLI seam), with a line-based reader of the first 4096 bytes. Cover the CRLF and BOM variants in the same test.
- [ ] 1.6 Drive "Two installs produce identical bytes" (CLI seam), rendering with sorted inputs and UTF-8 without a BOM.
- [ ] 1.7 Drive "No machine-specific values" (CLI seam).
- [ ] 1.8 Drive "LF line endings on Windows" (CLI seam, in the Windows CI job).
- [ ] 1.9 Drive "Project install" (CLI seam).
- [ ] 1.10 Drive "Windows profile path with a space" (CLI seam, in the Windows CI job).
- [ ] 1.11 Docs: create `docs/skill.md` with how the Skill is generated, the stamp format, and the table of install targets with POSIX and Windows paths.
- [ ] 1.12 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Replacing an installed Skill, and the result

- [ ] 2.1 Drive "Upgrade replaces an older Skill and removes stale files" (CLI seam). Add `packaging` for PEP 440 ordering, and the staged swap of design D5.
- [ ] 2.2 Drive "Newer Skill is kept" (CLI seam).
- [ ] 2.3 Drive "Hand-made Skill is kept" (CLI seam).
- [ ] 2.4 Drive "Force replaces a newer Skill" (CLI seam).
- [ ] 2.5 Drive "Incomplete install" (CLI seam): the partial result, exactly one `skill_install_incomplete` error diagnostic, and exit code 1.
- [ ] 2.6 Drive "Unknown target" (CLI seam): a usage error with nothing on stdout.
- [ ] 2.7 Drive "Locked file on Windows" (CLI seam, as a real subprocess with an open file handle in the Windows CI job). Add rollback, a rename retry of up to 1 s, and clean-up of the staging and backup folders.
- [ ] 2.8 Drive "Target error in the diagnostic shape" (CLI seam, in the Windows CI job): `skill_write_failed` as `{level, code, message, hint, details}`.
- [ ] 2.9 Docs: add an "Install the Skill" section to the README, and the replacement rules and `--force` to `docs/skill.md`.
- [ ] 2.10 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. SKILL.md: frontmatter, install and workflows

- [ ] 3.1 Drive "Frontmatter fields" and "Description names the trigger topics" (CLI seam). This is a trivial pair: both parse the same frontmatter. Keep the description at 1024 characters or fewer.
- [ ] 3.2 Drive "One-liners for every OS" (CLI seam).
- [ ] 3.3 Drive "Ask before installing" (CLI seam).
- [ ] 3.4 Drive "Quick check order" (CLI seam).
- [ ] 3.5 Drive "Full audit order" (CLI seam).
- [ ] 3.6 Drive "Recap is the last step" (CLI seam).
- [ ] 3.7 Drive "One subagent per Report Section" (CLI seam), with the subagent prompt template.
- [ ] 3.8 Drive "Notes file names come from the brief" (CLI seam), using `summary.md` and `section.notes_file` from `070-add-html-report`.
- [ ] 3.9 Drive "Report Section ids are listed" (CLI seam), from the accepted values of `report brief --section` in the command metadata.
- [ ] 3.10 Drive "Section Crawl flags" and "Segment guidance" (CLI seam). This is a trivial pair of text checks on neighbouring sections.
- [ ] 3.11 Docs: describe the install section and the three workflows in `docs/skill.md`.
- [ ] 3.12 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. SKILL.md: guardrails, hygiene and validity

- [ ] 4.1 Drive "Hand-off threshold" (CLI seam).
- [ ] 4.2 Drive "Unknown estimate is handed off" (CLI seam).
- [ ] 4.3 Drive "Hand-off uses the dry run's command" (CLI seam), using the `command.sh` and `command.powershell` of `060-add-crawl-control`.
- [ ] 4.4 Drive "Codex network and Workspace" (CLI seam).
- [ ] 4.5 Drive "Untrusted crawled text and the notice" (CLI seam).
- [ ] 4.6 Drive "Hygiene section" (CLI seam), with the advice to follow a running Crawl with `spider status`, not `spider summary`.
- [ ] 4.7 Drive "Line budget" and "Reference links resolve" (CLI seam). This is a trivial pair: both read the structure of the whole SKILL.md.
- [ ] 4.8 Drive "All command lines parse" (CLI seam). The lint extracts every `spider …` line from the fenced blocks of all installed files, replaces each `<placeholder>` with a sample value, and checks the result against `spider commands --format json`.
- [ ] 4.9 Docs: describe the Guardrails and output hygiene in `docs/skill.md`.
- [ ] 4.10 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Generated references

- [ ] 5.1 Drive "Headings match the Command list" (CLI seam) for `references/commands.md`.
- [ ] 5.2 Drive "Flags of skill install" (CLI seam).
- [ ] 5.3 Drive "Every Page data column is listed" (CLI seam) for `references/columns.md`, from `spider schema pages`.
- [ ] 5.4 Drive "Null-until release is shown" (CLI seam).
- [ ] 5.5 Drive "Every Rule is documented" (CLI seam) for `references/rules.md`, including thresholds with their `spider.toml` keys.
- [ ] 5.6 Drive "Every column is documented" (CLI seam) for `references/sql-schema.md`, generated from `spider schema --limit 1000 --format json` with each column's type, nullability, primary key, reference, format, allowed values and description (design D12). Add `render_tables(items, compact=...)` to `spider.services.schema_doc`, next to `018`'s `parse_tables`, with a pure-logic round-trip test (`parse_tables(render_tables(items)) == items`, for both modes), and read the installed file back with `parse_tables`.
- [ ] 5.7 Drive "Every index is documented" (CLI seam), with `no secondary index` for a table whose `indexes` is empty.
- [ ] 5.8 Drive "Every reference is in the joins section" (CLI seam): one `## Joins` line per column with a non-null `references`.
- [ ] 5.9 Drive "Schema version is stated" (CLI seam, with a Crawl of the local fixture site).
- [ ] 5.10 Drive "Minimum SQLite version is stated" (CLI seam).
- [ ] 5.11 Drive "URL and address section" (CLI seam), a written section of the template (design D12).
- [ ] 5.12 Drive "Pages and Resources section" (CLI seam), a written section of the template.
- [ ] 5.13 Drive "Cost of queries section" (CLI seam), a written section of the template. It names no index, because the generated lists carry them and the `links` indexes wait for `030`'s links benchmark.
- [ ] 5.14 Drive "Recipe SQL returns the expected rows" (CLI seam, with a Crawl of the local fixture site made once per test session). Write each recipe's expected rows by hand from the fixture's pages first, then run each fenced `sql` block with `spider sql` and compare the rows. A recipe without expected rows, or whose expected rows are empty, fails the test (design D13). Then write the recipes.
- [ ] 5.15 Drive "Header recipe reads response_headers" (CLI seam, with the same Crawl): add `/noindex-header` with `X-Robots-Tag: noindex` to the fixture site when it has no such page, and write the `json_each` recipe of design D13.
- [ ] 5.16 (v0.2) Drive "Segment recipe is valid" (CLI seam, with a Crawl of the local fixture site), using the `blog` and `shop` Segments in the `[segments]` table of `050-add-query-and-segments`.
- [ ] 5.17 Docs: list the five reference files and where each comes from in `docs/skill.md`, with which parts of `sql-schema.md` are generated and which are written, and how the recipes are checked.
- [ ] 5.18 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Outdated-Skill notice

- [ ] 6.1 Drive "Older user Skill for Claude Code" (CLI seam). Add a check that runs before Command dispatch and writes one `skill_outdated` warning through the stderr diagnostics writer of `010-add-workspace-and-cli-contract`. Register the code in `spider commands`.
- [ ] 6.2 Drive "Both user Skills are older" (CLI seam), with the hint builder for combined targets.
- [ ] 6.3 Drive "Older project Skill for Codex" (CLI seam).
- [ ] 6.4 Drive "Stdout and exit code are unchanged" (CLI seam).
- [ ] 6.5 Drive "Newer Skill is silent" (CLI seam).
- [ ] 6.6 Drive "Stamp beyond 4 KiB is ignored" (CLI seam).
- [ ] 6.7 Drive "A detached Crawl's log has no notice" (CLI seam, as a real `--detach` run against the local fixture site). The background process skips the check.
- [ ] 6.8 Docs: describe the notice, its diagnostic line, and where it is not printed in `docs/skill.md`.
- [ ] 6.9 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Developer script, repository copy and plugin marketplace

- [ ] 7.1 Drive "Script output equals the installed Skill" (install-and-packaging seam) with `scripts/generate_skill.py`, which calls the generator module.
- [ ] 7.2 Drive "Stale files are removed" (install-and-packaging seam).
- [ ] 7.3 Drive "Foreign folder is kept" (install-and-packaging seam).
- [ ] 7.4 Drive "One Skill in the plugin" (install-and-packaging seam). Commit `skills/spider/` as written by `scripts/generate_skill.py skills/spider`, and add `skills/** text eol=lf` to `.gitattributes`.
- [ ] 7.5 Drive "Plugin manifest" (install-and-packaging seam) by adding `.claude-plugin/plugin.json` with the `OWNER/REPO` placeholders.
- [ ] 7.6 Drive "Marketplace manifest" (install-and-packaging seam) by adding `.claude-plugin/marketplace.json`.
- [ ] 7.7 Drive "Copy and plugin share one version" (install-and-packaging seam).
- [ ] 7.8 Drive "Copy matches the generator at a release tag" (install-and-packaging seam) with a test marked `release`, which the release workflow of `085-add-release` runs. Check it on a commit whose copy was just regenerated, and again after changing one byte of the copy, when it must fail.
- [ ] 7.9 Docs: write README sections for the Claude Code plugin (`claude plugin marketplace add OWNER/REPO`, `claude plugin install spider@spider`), the Codex plugin (`codex plugin marketplace add OWNER/REPO`) and other agents (`npx skills add OWNER/REPO --skill spider`). Check each by hand against a local clone and record the results in the PR.
- [ ] 7.10 Docs: in `RELEASING.md`, add the release-commit steps: run `scripts/generate_skill.py skills/spider` and bump `plugin.json`.
- [ ] 7.11 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. `spider doctor` framework and local checks

- [ ] 8.1 Drive "Check ids and order" (CLI seam) with a check registry and the JSON report. Checks that are not built yet return `ok` until their own slice replaces them.
- [ ] 8.2 Drive "Counts add up" (CLI seam).
- [ ] 8.3 Drive "One row per check" (CLI seam) for `--format table`.
- [ ] 8.4 Drive "Only web URLs are accepted" (CLI seam): a usage error with nothing on stdout.
- [ ] 8.5 Drive "Supported range" (pure-logic seam).
- [ ] 8.6 Drive "Hint for an unsupported Python" (pure-logic seam).
- [ ] 8.7 Drive "The running interpreter" (CLI seam).
- [ ] 8.8 Drive "Version of the installed package" (CLI seam).
- [ ] 8.9 Drive "Missing compiled dependency" (pure-logic seam), with the package check's decision over literal import results.
- [ ] 8.10 Drive "SQLite version is reported" (CLI seam), from `sqlite3.sqlite_version`.
- [ ] 8.11 Drive "SQLite older than 3.37" (pure-logic seam), with the package check's decision over a literal SQLite version.
- [ ] 8.12 Drive "Not on PATH" (CLI seam).
- [ ] 8.13 Drive "A different spider comes first" (pure-logic seam), with the path check's decision over a literal command path and version.
- [ ] 8.14 Drive "Windows executable" (CLI seam, as a real subprocess in the Windows CI job).
- [ ] 8.15 Drive "Doctor does not print the notice" (CLI seam). `doctor` skips the outdated-Skill check.
- [ ] 8.16 Docs: create `docs/doctor.md` with every check id, what each status means, and the fixes, including the SQLite minimum of the `package` check and why crawl files need it.
- [ ] 8.17 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Doctor Workspace and WAL checks

- [ ] 9.1 Drive "Project Workspace" (CLI seam).
- [ ] 9.2 Drive "Global Workspace not created yet" (CLI seam), with a resolution mode that never creates the Workspace.
- [ ] 9.3 Drive "Global Workspace location blocked" (CLI seam).
- [ ] 9.4 Drive "Invalid settings" (CLI seam). Catch `settings_invalid` and report it inside the check, instead of letting the Command exit with code 3.
- [ ] 9.5 Drive "Nothing written" (CLI seam) by comparing the file trees under `<home>` and `<cwd>` before and after the run.
- [ ] 9.6 Drive "Non-ASCII path on the Windows console" (CLI seam, as a real subprocess with code page 437 in the Windows CI job).
- [ ] 9.7 Drive "Local disk" (CLI seam) through the journal-mode decision of `015-add-crawl-store`.
- [ ] 9.8 Drive "Network drive on Windows" (pure-logic seam), with the `wal` check's decision for the UNC path.
- [ ] 9.9 Drive "Rollback journal chosen in the settings" (CLI seam).
- [ ] 9.10 Docs: add Workspace and WAL troubleshooting to `docs/doctor.md`: network drives, `store.journal_mode`, and `spider init` in Codex.
- [ ] 9.11 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Doctor network and TLS checks, and the exit code

- [ ] 10.1 Drive "Local fixture site reachable" (HTTP fixture seam, through the CLI) with the network probe's TCP connect.
- [ ] 10.2 Drive "Refused connection" (HTTP fixture seam, with a closed local port), including the Codex fix in the hint.
- [ ] 10.3 Drive "A failed check" (CLI seam): exactly one `doctor_checks_failed` error diagnostic, and exit code 1.
- [ ] 10.4 Drive "Report still printed on failure" (CLI seam).
- [ ] 10.5 Drive "Overall status is the worst check status" (CLI seam).
- [ ] 10.6 Drive "Codex sandbox" (CLI seam, with the network probe double failing with a permission error).
- [ ] 10.7 Drive "Default target" (CLI seam, with the network probe double accepting `example.com`).
- [ ] 10.8 Drive "Connections only to the target" (HTTP fixture seam, with a recording network probe).
- [ ] 10.9 Drive "Proxy from the environment is reported and redacted" (CLI seam, with the network-probe double accepting and recording the connection). Add `details.proxy` using the proxy resolution of `022-add-fetch-policy`, the redaction of `015-add-crawl-store`, and doctor's `--proxy` flag.
- [ ] 10.10 Drive "Untrusted certificate" (HTTP fixture seam, against the HTTPS listener of `022-add-fetch-policy`). Add the verified handshake through 022's TLS setup, and `error_kind`.
- [ ] 10.11 Drive "Trusted certificate" (HTTP fixture seam, with the trust-store probe double containing the fixture's test CA).
- [ ] 10.12 Drive "Bundled fallback" (CLI seam, with the trust-store probe double).
- [ ] 10.13 Drive "No trust source at all" (CLI seam, with the trust-store probe double).
- [ ] 10.14 Drive "Not checked after a network failure" (HTTP fixture seam, with a closed local port).
- [ ] 10.15 Drive "Warnings keep exit code 0" (HTTP fixture seam, through the CLI).
- [ ] 10.16 Docs: add a troubleshooting section to `docs/doctor.md` covering:
  - Codex network access
  - proxies, including where the reported proxy comes from (`--proxy`, `spider.toml`, `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`)
  - TLS-inspecting antivirus
  - macOS `Install Certificates`
- [ ] 10.17 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Doctor Skill checks

- [ ] 11.1 Drive "Not installed" (CLI seam).
- [ ] 11.2 Drive "Current Skill" (CLI seam).
- [ ] 11.3 Drive "Outdated Codex Skill" (CLI seam).
- [ ] 11.4 Drive "Skill newer than the CLI" (CLI seam).
- [ ] 11.5 Drive "Hand-made project Skill" (CLI seam).
- [ ] 11.6 Docs: add the Skill checks and how to fix each warning to `docs/doctor.md`.
- [ ] 11.7 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Agent walkthrough and change review

- [ ] 12.1 Docs: write a Quick check and Full audit walkthrough in `docs/skill.md`. Run both by hand in Claude Code and in Codex against the local fixture site, and check each against the Guardrails:
  - the dry run comes first
  - a Hand-off happens when the estimate is above 5,000 URLs or `null`
  - there is one subagent per Report Section in Claude Code, and sequential Report Sections without subagents
  - the recap gives the Report path

  Record the transcripts in the PR.
- [ ] 12.2 Review: run the code-review skill on the whole change, then refactor with the whole suite green.
