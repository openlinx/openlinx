## Why

AI agents are spider's main users, but a CLI alone does not tell an agent when to crawl, how to keep its context small, when to hand a large Crawl to the user, or how to turn a Crawl into a Report. The Skill carries that know-how. It is generated from the installed CLI, so it cannot drift from the Commands it describes. `spider doctor` gives people and agents one Command that explains why spider cannot crawl on this machine, for example a network blocked by Codex, broken certificates, an unwritable Workspace or an outdated Skill.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships the generated Skill, `skill install`, the outdated-Skill notice, the repository copy and `doctor`; its install line is `uv tool install`. **Deferred to v0.2:** the Full audit workflow (it needs `070`), the dry-run guardrail and Hand-off (they need `060`), the install-script one-liners (`100`), `sql` recipes and Segments, `doctor --proxy`, and the plugin marketplace manifests.

- **Skill generation.** One generator module renders the Skill from the CLI's own metadata (Commands, Page data columns, Rules, the crawl store schema) and Markdown templates, and stamps it with the CLI version. Two callers use it:
  - `spider skill install`
  - the developer script `scripts/generate_skill.py <dir>`, which writes the repository copy. It is not a user Command.
- **What `SKILL.md` contains:**
  - frontmatter that triggers on SEO audit and crawl requests, and when to use the Skill.
  - the install instructions. This change owns the one-liners, with placeholder URLs, and `100-add-installers` builds the scripts behind them:
    - `curl -LsSf https://github.com/OWNER/REPO/releases/latest/download/install.sh | sh -s -- --yes --no-skill`
    - `powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://github.com/OWNER/REPO/releases/latest/download/install.ps1))) -Yes -NoSkill"`
    - `uv tool install --python 3.14 spider`
  - three workflows: **Quick check**, **Full audit** and **Section Crawl check**. The Full audit writes the Report with one subagent per Report Section, working from `spider report brief`. Agents without subagents do the Report Sections one after another. The workflow ends with a short chat recap and the Report's path.
  - when to use a Section Crawl and when to use Segments.
  - guardrails:
    - run a dry run first.
    - Hand-off of Crawls estimated above 5,000 URLs, or whose estimate is `null`.
    - ask before installing the CLI.
    - in Codex, ask for network approval.
    - treat crawled text as untrusted.
  - output hygiene: `--fields`, `--limit`, and `sql` for long-tail questions.
- **Generated references** in `references/`: `commands.md`, `columns.md`, `rules.md`, `sql-schema.md` and `recipes.md`.
- **New Command `spider skill install [--target claude|codex|all] [--project] [--force]`.**
  - It writes the Skill to `~/.claude/skills/spider/` and `~/.agents/skills/spider/`. With `--project` it writes to `.claude/skills/spider/` and `.agents/skills/spider/` in the current folder.
  - It replaces older generated copies. It will not replace a newer or hand-made Skill unless `--force` is given.
  - It prints a JSON result that lists every path it wrote. A target that fails carries an error in the full diagnostic shape.
- **Outdated-Skill notice.** When an installed Skill is older than the CLI, a Command writes one `skill_outdated` warning diagnostic to stderr. `skill install`, `doctor` and the background process of a detached Crawl never print it. `090-add-mcp-server` adds `mcp` to that list in v0.1.1. There is no environment variable to turn it off.
- **Repository copy and plugin marketplace.** The change adds:
  - a generated `skills/spider/` folder in the repository
  - `.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json`, with one plugin whose source is `./`

  With these, `claude plugin marketplace add`, `codex plugin marketplace add` and `npx skills add` all work from the GitHub repo. The plugin ships without an MCP config in v0.1. `090-add-mcp-server` adds it in v0.1.1.
- **New Command `spider doctor [--url <url>] [--proxy <url>]`.** It runs diagnostic checks. Each check reports a status (`ok`, `warn` or `fail`), a message and a hint.
  - It checks:
    - the Python version
    - the package and its compiled dependencies
    - `spider` on PATH
    - the Workspace
    - WAL support
    - outbound network, with the Codex `network_access` fix, and the proxy in effect. The proxy is reported with its source (flag, `spider.toml`, `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, or none) and with its password redacted as `user:***@host`.
    - TLS trust, through the TLS setup of `022-add-fetch-policy`
    - installed Skill versions per target
  - Output is JSON by default.
  - When a check fails, doctor prints the full report and exits 1 with one `doctor_checks_failed` error diagnostic.
  - `--url` points the network and TLS checks at a chosen site, such as a staging server (a small addition).
  - `--proxy` tests a proxy the way `spider crawl --proxy` of `022-add-fetch-policy` would use it (a small addition).
  - The `path` check backs the installers' PATH guidance (a small addition).

## Capabilities

### New Capabilities
- `agent-skill`: the generated, version-stamped Skill (SKILL.md and references), the developer generation script, `spider skill install`, the outdated-Skill notice, the repository copy and the plugin marketplace manifests.
- `diagnostics`: `spider doctor`, which covers its checks, statuses, hints, JSON and table output, and exit code.

### Modified Capabilities
(none)

## Non-goals

- Workflows for Commands that don't exist yet are added in the releases that bring those Commands:
  - `links`, `redirects`, `sitemaps`: **v0.2**
  - `diff`, `duplicates`, `structured-data`: **v0.3**
- The plugin's MCP server config (`.mcp.json`) belongs to `090-add-mcp-server`, in **v0.1.1**. The install scripts behind the one-liners, and the release pipeline, belong to `100-add-installers`.
- No `spider skill generate` Command. Generation for the repository is a developer script, as the maintainer decided on 2026-09-27.
- Local edits to an installed Skill are not preserved. Reinstalling replaces the whole folder. No release plans a merge.
- There is no `spider skill uninstall` in v0.1. The uninstall steps are documented by `100-add-installers`.
- `doctor` does not check PyPI for newer versions and makes no request other than to its target URL. This keeps the no-telemetry principle, and no release plans such a check.
- Agents other than those that read `.claude/skills` or `.agents/skills` use `npx skills add` until **v1.0** documents them.

## Impact

- **Code:**
  - `src/spider/skill/`: the generator, templates, stamp, installer and notice
  - `src/spider/cli/`: the `skill` and `doctor` groups
  - `src/spider/diagnostics/`: doctor's checks
  - `scripts/generate_skill.py`
- **Repository files:** `skills/spider/`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and a `.gitattributes` rule that keeps `skills/**` at LF line endings.
- **Depends on:**
  - `010-add-workspace-and-cli-contract`: the output contract, the diagnostic shape, exit codes, `commands --format json` and Workspace resolution
  - `015-add-crawl-store`: `schema --format json` and the journal-mode decision
  - `022-add-fetch-policy`: the TLS setup, and the HTTPS support of the fixture site
  - `040-add-rules`: `rules --format json`
  - `050-add-query-and-segments`: the Page data fields and the Segment syntax used in recipes
  - `060-add-crawl-control`: the dry-run `command` and `estimate`, `--detach`, and the background Crawl's log file
  - `070-add-html-report`: Report Section ids, `report brief` and the Report Notes file contract
- **Used by:**
  - `090-add-mcp-server` (v0.1.1): `doctor`, the plugin manifests and the outdated-Skill notice
  - `100-add-installers`: the scripts behind the one-liners, and the release check, which uses `scripts/generate_skill.py`
- **Dependencies:** Jinja2 for the Markdown templates, which it shares with the Report, and `packaging` for PEP 440 version comparison.
