> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md for the motivation. The facts the scripts must respect:
- **The URLs are already quoted.** `080-add-agent-skill` owns the one-liners that the Skill quotes, with placeholder URLs, including the options `--yes --no-skill` and `-Yes -NoSkill`. This change must serve scripts at exactly those URLs and implement those options.
- **uv installers.** uv 0.12.x downloads Python by itself. Astral's official installers are `curl -LsSf https://astral.sh/uv/install.sh | sh` and `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. They put uv in `~/.local/bin` (`%USERPROFILE%\.local\bin` on Windows) and add that folder to the user's PATH configuration.
- **`uv tool install` ignores `requires-python` when it picks an interpreter** (uv issue #14110). Python 3.15, released on 2026-10-01, has no wheels yet for aiohttp, selectolax, msgspec and zstandard, so an unpinned install on a machine whose newest Python is 3.15 fails. `uv tool upgrade <pkg>` upgrades a tool, and `uv tool update-shell` puts its bin folder on PATH.
- **`curl … | sh` feeds the script through stdin,** so prompts must read from `/dev/tty`.
- **In PowerShell, `irm … | iex` runs the script inside the caller's session,** so `exit` would close the user's window.
- **Codex runs commands with network access off by default,** so the installer's downloads fail inside the Codex sandbox until the user approves them.
- **The product name, the PyPI name and `OWNER/REPO` are placeholders.** Publishing needs a PyPI trusted-publisher entry for the final project name.

## Goals / Non-Goals

**Goals:**
- One command per OS that works on a fresh machine without administrator rights, can be run again safely, and is fully scriptable for agents (`--yes --no-skill`).
- Installer behaviour tested for real: real uv, a real wheel built from the checkout, real runners on all three OSes, before anything is published.
- A release that cannot publish a package whose Skill copy, plugin version or install path is broken.

**Non-Goals:**
- Replacing uv's own install logic. The scripts orchestrate uv; they do not reimplement it.
- Managing Python installations beyond `--python 3.14`.

## Decisions

### D1. Thin scripts that delegate to uv
uv gives isolated tool environments, Python downloads, upgrades and PATH handling on all three OSes. The scripts only glue these together and add three things of our own: verification, the Skill offer and clear exit codes.
- *Alternative:* our own Python bootstrap. It is a chicken-and-egg problem, because the user may have no Python.
- *Alternative:* pipx. It needs a working Python first and cannot download 3.14. It remains a documented developer option.
- *Alternative:* a zipapp. It still needs a compatible interpreter.

### D2. `--python 3.14`, one constant per script, and a test that ties them together
Each script declares `PYTHON_VERSION=3.14` (in PowerShell, `$PythonVersion = '3.14'`) once. A test checks that this value and `requires-python` agree. When the dependencies ship 3.15 wheels, one pull request raises `requires-python` and both constants together. In v0.1.1, `090-add-mcp-server` adds the bundle's `.python-version` to the same test.

### D3. Install, upgrade and reinstall commands
The script chooses its command by what `uv tool list` shows:
- **OpenLinx not installed:** `uv tool install --python 3.14 openlinx`
- **OpenLinx installed, no `--package`:** `uv tool upgrade openlinx`
- **`--package <spec>`:** `uv tool install --python 3.14 --reinstall <spec>`. This covers a wheel file, a pinned version or a git URL.

The old and new versions come from `uv tool list` before and after, and give the `linx <old> -> <new>` line. A later default run upgrades from a pinned spec only after `--package openlinx` resets it. The docs say so.

### D4. Minimum uv version 0.9.0
This is the first release with stable Python 3.14 downloads. Implementation re-checks the value and keeps it in one constant.
- When uv is older, the script runs `uv self update`.
- When uv came from a package manager, `uv self update` refuses. The script then stops with exit code 1 and a hint to upgrade uv the same way it was installed.

### D5. Agent detection is presence-based
- Claude Code counts as present when `~/.claude` exists or `claude` is on PATH.
- Codex counts as present when `~/.codex` exists or `codex` is on PATH.

Either sign is enough, because both folders are created on first use and the commands may not be on PATH in a fresh shell. The Skill goes to user-level folders only, and the script never uses `--project`. Tests use the folder signs only, so that no fake `claude` or `codex` program is ever needed.

### D6. Prompts
- **`install.sh`** reads its answers from `/dev/tty`. When `/dev/tty` cannot be opened (CI, agents, a new session without a controlling terminal) and `--yes` is not given, the script prints the commands to run later and skips the question.
- **`install.ps1`** asks with `Read-Host` only when the host is interactive and stdin is not redirected.

In both, the default answer is yes.

### D7. PowerShell specifics
- **Parameters:** there is no `[CmdletBinding()]`. The parameters are plain switches plus `-Package`, and leftover arguments land in `$args`. The script then prints usage and returns 2. This gives the same exit code 2 for `-Bogus` as `install.sh` gives for `--bogus`.
- **Exit:** when the script runs from a file (`$PSCommandPath` is set), it ends with `exit <code>`. Inside an existing session (`iex` or a script block), it sets `$global:LASTEXITCODE` and returns instead, so it never closes the user's window.
- **Downloads and errors:** the script sets `[Net.ServicePointManager]::SecurityProtocol` to TLS 1.2 or higher for Windows PowerShell 5.1 downloads, and `$ErrorActionPreference = 'Stop'` inside a try block that maps failures to exit codes.
- **Encoding:** the script saves `[Console]::OutputEncoding`, sets it to UTF-8 while `linx` runs so that paths with non-ASCII characters print correctly, and restores it afterwards.

### D8. Output format
- Steps print as `==> …` lines on stdout.
- Failures print as `error: …` and then `hint: …` on stderr.
- A dry run prints `would run: …` and `would ask: …` lines.
- Colour appears only on a terminal without `NO_COLOR`.

This format is plain enough for an agent to parse, and the tests assert on it.

### D9. The installers' own exit codes: 0, 1, 2 and 10
- These are separate from the CLI's table in `010-add-workspace-and-cli-contract`.
- 10 means "installed, but `linx doctor` found a failed check". It sits far from the small codes, so no one confuses it with a CLI code. An agent or CI job can then tell a broken install (1) from a machine problem, such as a blocked network or TLS inspection, that `doctor` already explained.
- When Codex's `CODEX_SANDBOX_NETWORK_DISABLED=1` is set, the hint for 1 explains the Codex fix. Reading that variable is detection, not a setting.

### D10. The release gates live in a small Python script
`scripts/release_check.py` holds the gates:
- the tag against the package version
- the Skill copy against a fresh run of `scripts/generate_skill.py` into a temporary folder
- the plugin version
- pre-release detection

Its output and exit codes can be tested locally with literal expected values. The workflow YAML stays glue.
- *Alternative:* inline shell in the workflow. It cannot be tested before a real tag is pushed.

### D11. Workflow shape
```
verify ──► build ──► smoke (ubuntu sh · macos sh · windows powershell 5.1 · windows pwsh 7) ──► publish ──► release ──► post-release check
```
- **`verify`** runs `release_check.py` and the full test suite, reusing the CI workflow of `000-scaffold-project`.
- **`build`** runs `uv build`, writes `SHA256SUMS`, and uploads the files as workflow artifacts. In v0.1.1, `090-add-mcp-server` adds `scripts/build_mcpb.py` to this job.
- **`smoke`** installs the built wheel with `--package`, so a broken package never reaches PyPI.
- **`publish`** uses `pypa/gh-action-pypi-publish` with trusted publishing. It needs `id-token: write` and the `pypi` environment, and it produces PEP 740 attestations.
  - *Alternative:* `uv publish`, which also supports trusted publishing. The official action is kept for its attestations and wide use.
- **`release`** runs `gh release create` with the assets, adding `--prerelease` when the gate says so.
- **`post-release check`** is not blocking. It runs the real `latest/download` one-liners on the three OSes and reports failures, because by then the package is already public.
- **Rehearsals:** a `workflow_dispatch` input rehearses the pipeline against TestPyPI.

### D12. Hosting
- GitHub release assets give `latest/download` URLs for free, and a fixed URL per version. Raw default-branch URLs stay available for testing unreleased scripts.
- The scripts install the latest release unless `--package` is given. A script is not stamped with its release's version, so re-running the latest one-liner always upgrades.

## Test seams

- **Install and packaging (8):** every installer scenario is tested here.
  - **Where:** the tests live in `tests/install/`. They run in the CI install job on `ubuntu-latest`, `macos-latest` and `windows-latest` (the last under both `powershell` 5.1 and `pwsh` 7), on pull requests that touch the scripts and in the release workflow's `smoke` job.
  - **What they use:**
    - the real scripts
    - real uv, either missing (removed from PATH) or installed:
      - 0.12 for the normal runs
      - 0.8.0 from its PyPI wheel, for "uv too old"
    - a wheel built from the checkout, passed with `--package`
    - a second wheel built with the version set to `0.0.1`, for "Upgrade reported"
  - **Isolation:** every run gets a new temporary home folder. On Windows, uv resolves some folders through OS APIs rather than `USERPROFILE`, so the tests also set `UV_INSTALL_DIR`, `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, `UV_PYTHON_INSTALL_DIR` and `UV_CACHE_DIR` inside it. These are uv's own variables, not settings of ours.
  - **Also covered here:**
    - the `--dry-run` plan
    - the `release_check.py` gates
    - the pin-consistency test
    - the parsed `release.yml` and `docs/installation.md`
    - the static search for `sudo` and `RunAs`
  - **Linters:** `shellcheck -s sh` and PSScriptAnalyzer run in CI.
- **No test doubles.** Our CLI is never replaced: every test that reaches `linx` runs the real one from the installed wheel. Agents are detected through the `~/.claude` and `~/.codex` folders, so no fake `claude` or `codex` program exists. The failure paths use real conditions:
  - a wheel path that does not exist
  - an `openlinx.toml` that makes `doctor` fail
  - a new session without a terminal

## Risks / Trade-offs

- **Installer tests are slow and need the network** (uv, Python 3.14 and dependencies from PyPI).
  - Mitigation: they run only in the CI install job, on pull requests that touch the scripts, and in releases. They are not part of the default local `pytest` run. uv's cache is shared between runs of one job.
- **`curl | sh` needs trust.**
  - Mitigation: HTTPS only, short and readable scripts, a documented "download, read, then run" alternative, and `SHA256SUMS` on every release.
- **Astral changes its installer or its URLs.**
  - Mitigation: the smoke tests on every release catch it, and the post-release check catches it after publishing.
- **The PyPI name is not settled.**
  - Mitigation: placeholders everywhere. Publishing stays blocked until the name is free on PyPI and GitHub, but nothing else is.
- **Corporate proxies and TLS inspection.**
  - Mitigation: uv honours `HTTPS_PROXY` and the system certificate store (with `--native-tls` when needed). The docs cover both, and `linx doctor`'s `tls` check explains failures after install (exit code 10).
- **GitHub runners have administrator rights,** so "no admin needed" cannot be shown by running without them.
  - Mitigation: the static check, the "only user-scoped locations" rule, and runs with the home folder and all uv folders inside a temporary folder.
- **A user who pastes `irm … | iex` into a constrained-language-mode session.**
  - Mitigation: the docs point to the `powershell -ExecutionPolicy ByPass -c` form, which starts a fresh process.

## Migration Plan

This is new functionality with nothing to migrate. When the product name is chosen:
1. Replace the placeholders in both scripts, the docs and the workflow, together with the constants of `080-add-agent-skill`.
2. Register the PyPI trusted publisher.
3. Cut `v0.1.0`.

Later changes to the Python pin follow D2.

## Open Questions

- Should the release copy of each script default to that release's version, for reproducible installs from a fixed URL? Right now it always installs the latest release unless `--package` is given.
- Should there be an `--uninstall` / `-Uninstall` mode, or should uninstalling stay documentation only? It would reuse the documented steps.
- Should the one-liners move to a short custom domain once the name is chosen? That would change the URLs in `080-add-agent-skill` as well.
- Should uv's `--native-tls` be passed automatically when the first download fails with a certificate error?
