# Codex execution

Read and edit project skills in `.agents/skills/`. Paths here are relative to the
repository root. `.claude/skills/<name>` aliases refer to the same physical
directories after the setup in [CONTRIBUTING.md](../CONTRIBUTING.md#set-up).

## Tools and permissions

- Read the complete SKILL.md explicitly; invoke a skill as `$skill-name` when the
  current session supports it. Resolve `references/` and `scripts/` from its directory.
- Names such as Read, Glob, Grep, Write, Edit and Bash describe operations in older
  procedures. Use available file tools, `rg` and the terminal. Run Bash syntax in
  Bash, or translate it to PowerShell with its quoting intact.
- AskUserQuestion means ask the user through an available channel. A required
  answer cannot be inferred from elapsed time; an executor passes the question
  to its coordinator.
- Tool lists, model hints and allowed-tools in workflow metadata do not configure
  Codex or grant permissions. Check actual tool availability before using MCP.
- When a workflow needs delegation and the user has authorized it, pass a complete
  brief and verify the result. Use existing sessions when the user assigns them.
  If delegation is unavailable, perform the checks sequentially and report that
  independent review is still needed.
- Platform-specific paths require their matching environment. Personal global
  skills and MCP credentials are installed separately; never copy credentials,
  caches or session logs into this repository.

## OpenSpec

| Claude entry | Canonical skill |
|---|---|
| `/opsx:explore` | `$openspec-explore` |
| `/opsx:propose` | `$openspec-propose` |
| `/opsx:apply` | `$openspec-apply-change` |
| `/opsx:sync` | `$openspec-sync-specs` |
| `/opsx:update` | `$openspec-update-change` |
| `/opsx:archive` | `$openspec-archive-change` |

Use the installed CLI and the paths it returns. Check that optional workflows
exist before recommending them; use the CLI fallback in SKILL.md otherwise.
Set `OPENSPEC_TELEMETRY=0` in the current shell before running OpenSpec.

Continue from [docs/development-state.md](../docs/development-state.md), checking
the current branch and task files. Historical memory and private handoff files
do not authorize push, merge or messages to others without the current assignment.
