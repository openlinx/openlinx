## MODIFIED Requirements

### Requirement: Outdated Skill notice
Before it runs, every Command SHALL check the Skill stamps in the four install locations: user level and project level, for `claude` and for `codex`. The project level is relative to the current folder. The check SHALL be skipped by:
- the Commands `skill install`, `doctor` and `mcp`
- the background process that runs a detached Crawl, whose output is the Crawl's log file (`060-add-crawl-control`)

When at least one stamped Skill has a lower PEP 440 version than the CLI, the Command SHALL write exactly one diagnostic line to stderr, in the diagnostic shape of `010-add-workspace-and-cli-contract`, with:
- `level`: `"warning"`
- `code`: `"skill_outdated"`
- `message`: names each outdated location and its version
- `hint`: the `spider skill install` command, or commands joined with ` && `, that updates every outdated location
- `details.locations`: one entry `{target, scope, path, installed_version}` for each outdated location
- `details.cli_version`: the CLI version

The notice SHALL NOT change stdout or the exit code. The check SHALL:
- read at most the first 4096 bytes of each `SKILL.md`
- make no network connection
- ignore folders that are missing, unreadable, unstamped, or stamped with the CLI version or a newer one

#### Scenario: Older user Skill for Claude Code
- **WHEN** `<home>/.claude/skills/spider/SKILL.md` is stamped `0.0.1` and `spider schema` runs
- **THEN** stderr contains exactly one line that parses as JSON with `level` `"warning"`, `code` `"skill_outdated"` and `hint` `"spider skill install --target claude"`

#### Scenario: Both user Skills are older
- **WHEN** both `<home>/.claude/skills/spider/SKILL.md` and `<home>/.agents/skills/spider/SKILL.md` are stamped `0.0.1` and `spider schema` runs
- **THEN** the `skill_outdated` diagnostic has `hint` `"spider skill install --target all"` and two entries in `details.locations`

#### Scenario: Older project Skill for Codex
- **WHEN** `.agents/skills/spider/SKILL.md` in the current folder is stamped `0.0.1` and `spider schema` runs
- **THEN** the `skill_outdated` diagnostic has `hint` `"spider skill install --target codex --project"`

#### Scenario: Stdout and exit code are unchanged
- **WHEN** `spider schema` runs once with a Skill stamped `0.0.1` installed and once with no Skill installed
- **THEN** both runs produce byte-identical stdout and the same exit code

#### Scenario: Newer Skill is silent
- **WHEN** the only installed Skill is stamped `999.0.0` and `spider schema` runs
- **THEN** stderr contains no line with `skill_outdated`

#### Scenario: Stamp beyond 4 KiB is ignored
- **WHEN** the only installed `SKILL.md` puts 5000 bytes of frontmatter comments before a `metadata.version` of `0.0.1`, and `spider schema` runs
- **THEN** stderr contains no line with `skill_outdated`

#### Scenario: Doctor does not print the notice
- **WHEN** a Skill stamped `0.0.1` is installed and `spider doctor` runs
- **THEN** stderr contains no line with `skill_outdated`

#### Scenario: The MCP server does not print the notice
- **WHEN** a Skill stamped `0.0.1` is installed, and `spider mcp` runs as a subprocess until a client connects, lists the tools and closes its input
- **THEN** the subprocess's stderr contains no line with `skill_outdated`

#### Scenario: A detached Crawl's log has no notice
- **WHEN** a Skill stamped `0.0.1` is installed, and a Crawl started with `spider crawl <fixture-url> --detach` has completed
- **THEN** the file named by the result's `log_file` contains no line with `skill_outdated`
