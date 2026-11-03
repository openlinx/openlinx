@AGENTS.md

## Claude Code

The import above supplies the shared rules. Run the development setup in
CONTRIBUTING.md to restore `.claude/skills/<name>` as local aliases to
`.agents/skills/<name>`. Edit skill content only through `.agents/skills/`.
The current session determines which tools and permissions are available.

The `/opsx:*` commands in `.claude/commands/opsx/` load the corresponding canonical
SKILL.md and pass their arguments through to it.
