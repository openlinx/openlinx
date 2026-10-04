> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md for the motivation. This change adds no crawl behaviour. It packages knowledge that other changes own:
- the output contract, diagnostics and Command metadata: `010-add-workspace-and-cli-contract`
- the crawl store schema and the journal-mode decision: `015-add-crawl-store`
- the TLS setup and the HTTPS fixture site: `022-add-fetch-policy`
- Rules: `040-add-rules`
- Page data columns and Segments: `030-add-page-data` and `050-add-query-and-segments`
- dry run, detach and the background Crawl's log file: `060-add-crawl-control`
- Report Sections and Report Notes: `070-add-html-report`

The Skill has to stay correct as those change, so everything that can be generated from metadata is generated.

The Skill is read in several places, and each reads it differently:
- **Claude Code** reads `~/.claude/skills/<name>/SKILL.md`, and in a project `.claude/skills/<name>/SKILL.md`.
- **Codex** and most other agents (Cursor, Copilot, Gemini CLI, OpenCode, goose, Zed, Junie) read `~/.agents/skills` and `.agents/skills`.
- **Plugin marketplaces** (Claude Code and Codex) read `.claude-plugin/marketplace.json`. With `"source": "./"`, the repository root is the plugin root, so the plugin's Skill must sit at `skills/<name>/SKILL.md`.
- **`npx skills add owner/repo`** searches the repository for `SKILL.md` files.

Codex runs commands with network access switched off by default. It can write only inside the project, so `~/.spider/` and `~/.agents/skills/` are read-only there unless the user approves.

Settings never come from environment variables (`010-add-workspace-and-cli-contract`). There are two exceptions this change relies on:
- the standard proxy variables `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY`, which `022-add-fetch-policy` honours for fetching
- read-only host-agent signals such as Codex's `CODEX_SANDBOX_NETWORK_DISABLED`, which are used only for detection and hints

## Goals / Non-Goals

**Goals:**
- One generator whose output is byte-identical for a given CLI version, used by `skill install` and by the developer script that writes the repository copy.
- A stamp that can be read in well under a millisecond, so every Command can afford the outdated-Skill check.
- `doctor` checks that work offline where they can, and that name the exact fix.

**Non-Goals:**
- Teaching SEO. The Skill teaches how to drive spider. Rule texts carry the SEO guidance, and the agent supplies the judgement (ADR-0004).
- Detecting stale plugin-installed Skills from the CLI side. That would mean reading the plugin caches of Claude Code and Codex. SKILL.md asks the agent to compare its stamp with `spider --version` instead.

## Decisions

### D1. One generator, two callers
The generator module reads the same in-process metadata that `spider commands|schema|rules --format json` print, and renders Markdown templates that ship in the package. It has two callers:
- `spider skill install`, which writes into the agents' skills folders
- `scripts/generate_skill.py <dir>`, a developer script that writes the repository copy and is used by the release check of `100-add-installers`

Alternatives considered:
- *A `spider skill generate` Command.* The maintainer decided against it on 2026-09-27. Generating into an arbitrary folder is a developer need, not a user one, and it would widen the Command surface that the Skill itself must document.
- *Static Markdown shipped in the wheel.* It would drift from the Commands.

### D2. Jinja2 Markdown templates with fixed placeholders
- Templates live in `src/spider/skill/templates/` and render with `StrictUndefined`, no autoescaping (the output is Markdown) and sorted inputs.
- A single constants module holds:
  - the CLI name, the package name and the Skill name
  - the `OWNER/REPO` placeholder
  - the install one-liners
  - the Hand-off threshold of 5,000

  When the product name is chosen, that one module is edited and the Skill is regenerated.
- This change owns the one-liners' text, and `100-add-installers` must serve scripts at those URLs that accept `--yes --no-skill` and `-Yes -NoSkill`.
- *Alternative:* `string.Template`. It uses `$` placeholders, which collide with the `$HOME` and `$env:Path` shell examples.

### D3. The stamp lives in the SKILL.md frontmatter `metadata`
`metadata: {generator: spider, version: "X.Y.Z"}` is part of the open Agent Skills format, and it travels with every install channel: `skill install`, plugins, `npx skills add` and manual copies.
- The reader parses only the first 4 KiB, using a small line parser and no YAML library on the hot path.
- *Alternative:* a sidecar `.spider-skill.json`. It is cheaper to parse, but `npx skills add` or a manual copy may drop it, and then the stamp is gone.

### D4. The notice is one warning diagnostic on stderr
- It uses the stderr diagnostic shape of `010-add-workspace-and-cli-contract`: `{"level": "warning", "code": "skill_outdated", "message", "hint", "details"}`. Agents already parse that shape. The level `warning`, together with an unchanged exit code, keeps it apart from errors. The code is registered in `spider commands`.
- **Where it is not printed:**
  - `skill install`, which fixes it.
  - `doctor`, which reports the same thing as checks.
  - the background process of a detached Crawl, whose stderr is the Crawl's log file. The Crawl specs speak of the "first event line", so a notice from the foreground `crawl` Command cannot shift their events.
  - `mcp`, whose stderr is a client log. `090-add-mcp-server` adds it to this list in v0.1.1.
- **Cost:** at most four `open()` + `read(4096)` calls, with no network.
- **Only an older Skill triggers it.** A newer Skill means the CLI is out of date. SKILL.md and `doctor` handle that case.
- **No off switch.** Environment variables are not settings, and a flag on every Command would be noise. Updating or removing the outdated Skill ends the notice.
- *Alternative:* a field in the stdout JSON. That would change the output contract, and CSV and table output have no place for it.

### D5. Staged replacement for install
1. The new Skill is rendered into a staging folder next to the skills folder (`~/.claude/.spider-staging-<random>/spider`), never inside it. Agents load any folder under `skills/` that holds a `SKILL.md`, so a stray copy there would be loaded as a second skill.
2. The old folder is renamed to a backup next to the skills folder.
3. The staging folder is renamed into place.
4. The backup is deleted.

If any rename fails (for example, Windows refuses to rename a folder while a file inside it is open), the steps are rolled back and the target is reported as `failed`, with a `skill_write_failed` error in the full diagnostic shape. Stale files disappear because the whole folder is replaced. Renames are retried for up to 1 s, because indexers and antivirus scanners briefly lock new files.
- *Alternative:* overwrite file by file. A failure then leaves a mix of versions and a misleading stamp.

### D6. Refusal rules
- `skill install` refuses a newer stamp or an unstamped folder unless `--force` is given. An older CLI should not silently downgrade a Skill, and a hand-made `spider` Skill is the user's own work.
- `scripts/generate_skill.py` refuses only a non-empty unstamped folder. It is a release tool, so downgrades are normal there, but a mistaken target must not wipe a folder.

### D7. The repository copy changes only in release commits
The plugin marketplace and `npx skills add` read the default branch. If the copy were regenerated on every pull request, `main` would describe Commands that are not on PyPI yet.
- The release commit regenerates `skills/spider/` and bumps `.claude-plugin/plugin.json`.
- The release pipeline of `100-add-installers` regenerates into a temporary folder with `scripts/generate_skill.py`, and fails if the committed copy differs.
- A `.gitattributes` line `skills/** text eol=lf` keeps Windows checkouts byte-identical.

### D8. Plugin manifests
- `plugin.json` carries `version`. `marketplace.json` leaves `version` out of its entry, so it is maintained in one place.
- The plugin ships without `.mcp.json` in v0.1. `090-add-mcp-server` adds it at the plugin root in v0.1.1.
- *Alternative:* a `plugin/` subfolder as the source. It would hide `src/` from the plugin cache, but it moves the Skill away from the standard `skills/` path that `npx skills add` expects.

### D9. Naming: "guardrails", not "rules"
The agent guidance section is called Guardrails, because Rule is a glossary term (an SEO check). Doctor's diagnostic "checks" are unrelated to Rules.

### D10. Doctor design
- **Structure:** each check is a small function returning `{id, status, message, hint, details}`. A registry fixes the order. `status` and `counts` are derived from the checks.
- **Decision logic is pure.** It can be tested with literal inputs at the pure-logic seam:
  - the Python range
  - the import results of the `package` check
  - the version comparison of the `path` check
  - the journal-mode outcome of the `wal` check
  - the Skill statuses

  Only the thin probes around it touch the system.
- **Exit codes** follow `010-add-workspace-and-cli-contract`.
  - A failed check is a partial result: the report goes to stdout, and exactly one `doctor_checks_failed` error diagnostic goes to stderr, with exit code 1.
  - A bad `--url` is a usage error (2), with nothing on stdout.
  - An invalid `spider.toml` is reported inside the `workspace` check, so doctor does not exit with code 3.
- **`network`:**
  - It opens a TCP connection through the network probe (DNS, then connect) to the target host, or to the proxy that a Crawl would use. It sends no HTTP request.
  - `tls` then performs the verified handshake. Keeping the two apart tells "cannot reach" from "cannot trust".
  - The default target is `https://example.com/`, which is IANA-reserved and neutral. No other host is contacted, so doctor sends no telemetry.
  - **The proxy in effect** is found with the proxy resolution of `022-add-fetch-policy`, so doctor tests what a Crawl would use:
    - precedence: `--proxy`, then the proxy setting in `spider.toml`, then `HTTP_PROXY`/`HTTPS_PROXY` for the target's scheme unless `NO_PROXY` excludes the host
    - it is reported as `details.proxy = {source, url}`, with the password redacted by the partial redaction of `015-add-crawl-store` (`user:***@host`)
    - `--proxy` mirrors `spider crawl --proxy`, so a proxy can be tested before a Crawl
- **Codex's signal:** `CODEX_SANDBOX_NETWORK_DISABLED` is read-only. It only changes the message and hint, never a setting.
- **Codex detection:** Codex's `CODEX_SANDBOX_NETWORK_DISABLED=1`, or a connect that fails with a permission error (EPERM or EACCES), leads the message with the sandbox cause. The hint always includes the Codex fix, so the check stays correct if Codex renames its variable.
- **`tls`:**
  - It calls the TLS setup of `022-add-fetch-policy`, where truststore means `system` and the certifi fallback means `bundled`. It gets that setup's trust store through the trust-store probe, so doctor and a Crawl never disagree.
  - `error_kind` normalises OS-specific error messages. truststore's messages differ on Windows, macOS and Linux.
- **`wal`** calls the journal-mode decision of `015-add-crawl-store`, which covers the `store.journal_mode` setting and network locations (UNC paths, mapped drives and network file systems). An explicit `delete` setting is the user's choice, so only the automatic fallback warns.
- **`path`** runs the first `spider` on PATH with `--version`. Comparing versions works on every OS, including uv's Windows trampolines, where comparing file paths does not.
- **`workspace`** uses a resolution mode that never creates the global Workspace. The creatability probe makes a temporary folder in the nearest existing ancestor and removes it.

### D11. PEP 440 comparison with `packaging`
Version comparison uses `packaging.version.Version`, so that `0.2.0.dev1 < 0.2.0` holds. `packaging` is small, pure Python and ubiquitous.
- *Alternative:* comparing tuples by hand. It mishandles pre-releases and dev versions.

## Test seams

The seams are those of docs/testing.md:
- **CLI (1):** covers `skill install`, the Skill's content (read from the installed folder), the notice and `doctor`, tested in-process with `CliRunner`.
  - Every test sets the home folder (`HOME` on POSIX, `USERPROFILE` on Windows) and the current folder to temporary folders.
  - Real subprocess runs are used only for three cases: the Windows locked-file case, the code-page-437 console case, and the detached Crawl whose log is checked for the notice.
  - Stamps `0.0.1` and `999.0.0` stand for "older" and "newer", so no test needs to fake the CLI version.
- **HTTP fixture site (3):**
  - `network` checks against the plain-HTTP fixture site of `000-scaffold-project`, and uses a closed local port for "unreachable".
  - `tls` checks against the HTTPS listener and test CA that `022-add-fetch-policy` adds to the fixture site. This change adds no fixture support of its own.
- **Pure-logic modules (4):**
  - the stamp reader (CRLF, BOM, stamp beyond 4 KiB, missing frontmatter)
  - PEP 440 ordering
  - the notice's hint builder
  - doctor's decision logic (D10)
- **Install and packaging (8):** repository artefacts:
  - `scripts/generate_skill.py` output compared with the installed Skill and with `skills/spider/`
  - `.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json`
- **Boundary doubles:** only the two that docs/testing.md allows for `doctor`:
  - the **network probe**: a recording probe, success for `example.com`, and a permission error for the Codex case
  - the **trust-store probe**: the system store unavailable, bundled only, none, or a store that contains the fixture's test CA

  No other part of this change is replaced by a double.

## Risks / Trade-offs

- **Agents change their skill folders.**
  - Mitigation: the paths live in one table in the code, and `doctor` shows where it looked.
- **`npx skills add OWNER/REPO` also finds this repository's development skills in `.claude/skills/openspec-*` and `.agents/skills/openspec-*`.**
  - Mitigation: the docs use `npx skills add OWNER/REPO --skill spider`.
- **Duplicate Skills when a user installs both the plugin and `skill install`.**
  - Mitigation: the install one-liners in SKILL.md pass `--no-skill`, and the docs recommend one channel per agent.
- **Recipes or command examples rot as other changes evolve.**
  - Mitigation: the recipe SQL runs against a fixture Crawl, and every `spider …` line is linted against the command metadata in CI.
- **A notice on every Command is noisy, and there is no off switch.**
  - Mitigation: it is one line on stderr, and it disappears after `spider skill install`.
- **Upstream metadata is not ready when this change starts.**
  - Mitigation: this change is built after 070 in the build order. The reference tests compare against whatever `spider commands`, `schema` and `rules` list.

## Migration Plan

This is new functionality with nothing to migrate. When the product name changes:
1. Edit the constants module (D2).
2. Regenerate `skills/spider/` with `scripts/generate_skill.py`.
3. Rename the plugin.

Users then reinstall the Skill with `spider skill install --force`, because the folder name changes.

## Open Questions

- Should `skill install` follow `CLAUDE_CONFIG_DIR` when it is set, so that Claude Code reads the relocated folder? The default paths above do not change either way.
- Does Codex need a `.codex-plugin/plugin.json` in addition to reading `.claude-plugin/`? Check with `codex plugin marketplace add` during implementation. It would be an extra file only.
- Is a `spider skill uninstall` Command worth adding after v0.1? The uninstall instructions of `100-add-installers` delete the folders by hand for now.
- Should the development-only OpenSpec skills move out of the repository root, so that `npx skills add` without `--skill` lists only the spider Skill?
