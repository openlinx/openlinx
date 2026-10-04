## Why

Most people who ask an agent for an SEO audit have no Python set up, and the agent needs a CLI it can install after one yes from the user. The Skill of `080-add-agent-skill` already quotes one install command per operating system. This change builds the scripts behind those commands. The scripts must:
- work on a fresh machine without administrator rights
- pin a Python that every dependency has wheels for
- verify the install
- offer the Skill to the agents they find

Every release must also publish the same artifacts reproducibly: the PyPI package and the install scripts. The repository's Skill copy must match the release.

## What Changes

> **Scope (2026-10-05, see ROADMAP.md):** this change is **v0.2** and keeps only the install scripts, their options and their exit codes. The release pipeline below (the tag workflow, `release_check.py` with the Skill-copy check, `uv build`, PyPI trusted publishing and the GitHub release) and the documented developer install move to `085-add-release` in v0.1. This change then adds its scripts and their smoke tests to 085's workflow.

- **`scripts/install.sh` (POSIX `sh`, macOS and Linux) and `scripts/install.ps1` (Windows PowerShell 5.1 and PowerShell 7).**
  - They are served at the URLs that `080-add-agent-skill` quotes, as GitHub release assets:
    - macOS and Linux: `curl -LsSf https://github.com/OWNER/REPO/releases/latest/download/install.sh | sh`
    - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://github.com/OWNER/REPO/releases/latest/download/install.ps1 | iex"`
  - They are also available as raw files on the default branch.
  - The scripts:
    1. find uv, or install it with Astral's official installer. When uv is older than the declared minimum, they run `uv self update`.
    2. run `uv tool install --python 3.14 spider` on first install, and `uv tool upgrade spider` when the script runs again.
    3. make sure the tool's bin folder is on PATH (`uv tool update-shell`), and print the command that adds it to PATH in the current terminal.
    4. verify the install with `spider --version` and `spider doctor --format table`.
    5. detect Claude Code and Codex, and ask before running `spider skill install --target claude|codex` for each.
- **Options, the same in both scripts:**
  - `--yes` / `-Yes`: no prompts, and install the Skill for every detected agent.
  - `--no-skill` / `-NoSkill`: skip the Skill step.
  - Small additions:
    - `--package <spec>` / `-Package <spec>` installs a wheel or a pinned spec. Every installer test uses it with a locally built wheel.
    - `--no-modify-path` / `-NoModifyPath` leaves shell profiles and the user PATH alone.
    - `--dry-run` / `-DryRun` prints the plan and changes nothing.
    - `--help` / `-Help` prints usage and the uninstall steps.
- **Installer exit codes,** separate from the CLI's own table:
  - 0: installed
  - 1: failed
  - 2: invalid options
  - 10: installed, but `spider doctor` reported a failed check
- **Release pipeline `.github/workflows/release.yml`,** triggered by `v*` tags:
  1. gates in `scripts/release_check.py` (a small addition):
     - the tag matches the package version.
     - `scripts/generate_skill.py` from `080-add-agent-skill`, run into a temporary folder, produces exactly the committed `skills/spider/`.
     - the plugin version matches.
  2. the test suite.
  3. `uv build` (wheel and sdist).
  4. install-script smoke tests with the built wheel on Windows (PowerShell 5.1 and 7), macOS and Linux.
  5. PyPI trusted publishing.
  6. a GitHub release with the wheel, the sdist, both scripts and `SHA256SUMS`.
- **Python pin.** The package declares `requires-python = ">=3.12,<3.15"`, and the installers pass `--python 3.14`. This is needed because `uv tool install` ignores `requires-python` when it picks an interpreter (uv issue #14110), and Python 3.15 has no wheels yet for aiohttp, selectolax, msgspec and zstandard. A consistency test guards the pin, and the docs explain it.
- **Documentation.**
  - `docs/installation.md` covers:
    - install and options
    - what changes on the machine
    - upgrade and uninstall
    - the developer install with `uv tool install --python 3.14 spider` or `pipx install --python 3.14 spider`
    - troubleshooting
  - `RELEASING.md` covers the release process.

## Capabilities

### New Capabilities
- `installation`: the install scripts and their options, plans, output and exit codes; the Python pin; hosting; the developer install; and the tag-triggered release pipeline with its gates, smoke tests and published artifacts.

### Modified Capabilities
(none)

## Non-goals

- Signed standalone binaries and winget come **after v1.0** (Backlog: distribution).
- A Homebrew tap, a Scoop bucket and a multi-arch Docker image on GHCR come in **v1.0**.
- A short custom domain for the one-liners comes after the product name is chosen. Until then `OWNER/REPO` and `spider` are placeholders. Publishing is blocked until the name is free on PyPI and GitHub, but the specs are not.
- An `--uninstall` mode is not part of v0.1. The uninstall steps are documented only, and the mode is an open question.
- Offline or air-gapped installation is not planned.
- The `.mcpb` bundle is not a v0.1 release asset. It comes with the MCP server in **v0.1.1** (`090-add-mcp-server`).

## Impact

- **New files:**
  - `scripts/install.sh`, `scripts/install.ps1`, `scripts/release_check.py`
  - `.github/workflows/release.yml`
  - `docs/installation.md`, `RELEASING.md`
  - tests under `tests/install/`, which run in the CI install job against a locally built wheel
- **Changed:** `pyproject.toml` gets the Python 3.12–3.14 classifiers. `000-scaffold-project` already sets `requires-python = ">=3.12,<3.15"`, and this change's consistency test guards it.
- **Depends on:**
  - `000-scaffold-project`: pyproject, the CI workflow (which the release workflow reuses) and Node in CI
  - `080-add-agent-skill`: the one-liners the scripts must serve, `spider doctor`, `spider skill install`, `scripts/generate_skill.py`, `skills/spider/` and `.claude-plugin/plugin.json`
- **Used by:** `090-add-mcp-server` in v0.1.1, which adds the `.mcpb` bundle to the `build` and `release` jobs and its `.python-version` to the pin test.
- **External:**
  - Astral's installers at `astral.sh`
  - a PyPI trusted-publisher entry, which needs the final project name
  - the GitHub-hosted Windows, macOS and Linux runners
