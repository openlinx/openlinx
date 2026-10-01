## Purpose

Installs, upgrades and checks spider with one command per operating system, and publishes each release to PyPI and GitHub with the artifacts that people and agents install from.

## ADDED Requirements

### Requirement: One-command install scripts
The project SHALL provide two install scripts, served at the URLs that the Skill of `080-add-agent-skill` quotes:
- `scripts/install.sh`, for POSIX `sh` on macOS and Linux
- `scripts/install.ps1`, for Windows PowerShell 5.1 and PowerShell 7

The documented one-liners SHALL be:
- `curl -LsSf https://github.com/OWNER/REPO/releases/latest/download/install.sh | sh`
- `powershell -ExecutionPolicy ByPass -c "irm https://github.com/OWNER/REPO/releases/latest/download/install.ps1 | iex"`

Both scripts SHALL accept the same options:

| `install.sh` | `install.ps1` |
|---|---|
| `--yes`, `-y` | `-Yes` |
| `--no-skill` | `-NoSkill` |
| `--package <spec>` | `-Package <spec>` |
| `--no-modify-path` | `-NoModifyPath` |
| `--dry-run` | `-DryRun` |
| `--help` | `-Help` |

Options SHALL be passable to piped scripts: `curl … | sh -s -- <options>`, and `& ([scriptblock]::Create((irm <url>))) <options>` in PowerShell. `OWNER/REPO` and the package and command name `spider` are placeholders until the product name is chosen.

#### Scenario: Unknown option in sh
- **WHEN** `sh scripts/install.sh --bogus` runs
- **THEN** the exit code is 2 and stderr contains `usage:`

#### Scenario: Unknown option in PowerShell
- **WHEN** `powershell -ExecutionPolicy ByPass -File scripts/install.ps1 -Bogus` runs on Windows
- **THEN** the exit code is 2 and stderr contains `usage:`

### Requirement: Install plan
The scripts SHALL decide their actions in this order:
1. uv
2. install or upgrade
3. PATH
4. verification
5. the Skill

With `--dry-run`, they SHALL print each action on its own line, as `would run: <exact command>` or `would ask: <question>`, and exit 0. Commands of the installed tool SHALL appear by name (`spider …`), not by path. A dry run SHALL NOT download, install or change anything. It may only ask uv for its version, its installed tools and its bin folder.

#### Scenario: First install plan
- **WHEN** `sh scripts/install.sh --dry-run` runs with uv 0.12 on PATH, no tool installed, and an empty home folder
- **THEN** stdout contains the line `would run: uv tool install --python 3.14 spider`

#### Scenario: Dry run changes nothing
- **WHEN** `sh scripts/install.sh --dry-run --yes` runs with uv 0.12 on PATH and a home folder that holds only a `.claude` folder
- **THEN** the files under the home folder are the same before and after the run

### Requirement: uv bootstrap
The scripts SHALL look for uv in this order:
1. on PATH
2. in `$UV_INSTALL_DIR` or `$XDG_BIN_HOME`
3. in `~/.local/bin`, which is `%USERPROFILE%\.local\bin` on Windows

When no uv is found, the scripts SHALL install it with Astral's official installer and use it by absolute path for the rest of the run. When the found uv is older than 0.9.0, the minimum version the scripts declare, they SHALL run `uv self update`. If that fails, they SHALL exit with code 1 and a hint.

#### Scenario: uv missing on macOS or Linux
- **WHEN** `sh scripts/install.sh --dry-run` runs with no `uv` on PATH and an empty home folder
- **THEN** stdout contains the line `would run: curl -LsSf https://astral.sh/uv/install.sh | sh`

#### Scenario: uv missing on Windows
- **WHEN** `scripts/install.ps1 -DryRun` runs on Windows with no `uv` on PATH and an empty profile folder
- **THEN** stdout contains the line `would run: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

#### Scenario: uv too old
- **WHEN** `sh scripts/install.sh --dry-run` runs with uv 0.8.0, installed from PyPI into a temporary folder, first on PATH
- **THEN** stdout contains the line `would run: uv self update`

#### Scenario: uv installed into the home folder
- **WHEN** `sh scripts/install.sh --yes --package <wheel>` runs on a CI runner with no uv on PATH and the home folder set to the new temporary folder `<home>`
- **THEN** `<home>/.local/bin/uv` exists after the run

### Requirement: Install with a pinned Python
On first install the scripts SHALL run `uv tool install --python 3.14 spider`. With `--package <spec>` they SHALL run `uv tool install --python 3.14 --reinstall <spec>` instead. The tool therefore always runs on Python 3.14, whichever Python versions are present, and uv downloads Python 3.14 when it is missing.

#### Scenario: Package spec
- **WHEN** `sh scripts/install.sh --dry-run --package <wheel>` runs with uv 0.12 on PATH, where `<wheel>` is the path of the locally built wheel
- **THEN** stdout contains the line `would run: uv tool install --python 3.14 --reinstall <wheel>`

#### Scenario: Successful install
- **WHEN** `sh scripts/install.sh --no-skill --package <wheel>` runs on a CI runner with a new temporary home folder
- **THEN** the exit code is 0, and `spider --version`, run from uv's tool bin folder, prints the version of `<wheel>`

### Requirement: Re-running upgrades
When uv lists spider as an installed tool and `--package` is not given, the scripts SHALL run `uv tool upgrade spider`. With `--package` they SHALL reinstall from that spec. Either way, they SHALL print `spider <old> -> <new>` when the version changed, and `spider is already up to date` when it did not. Running the scripts again SHALL be safe at any time.

#### Scenario: Upgrade plan
- **WHEN** `sh scripts/install.sh --dry-run` runs after `<wheel>` was installed as a uv tool
- **THEN** stdout contains the line `would run: uv tool upgrade spider`

#### Scenario: Upgrade reported
- **WHEN** a wheel built from the same source with the version set to `0.0.1` is installed first, and `sh scripts/install.sh --no-skill --package <wheel>` then runs
- **THEN** stdout contains `spider 0.0.1 -> <version>`, where `<version>` is the version of `<wheel>`

#### Scenario: Already up to date
- **WHEN** `sh scripts/install.sh --no-skill --package <wheel>` runs twice on the same runner
- **THEN** the second run exits with code 0, and its stdout contains `spider is already up to date`

### Requirement: Verification after install
After installing or upgrading, the scripts SHALL run `spider --version` and `spider doctor --format table`, using the absolute path in uv's tool bin folder, and SHALL show their output.
- When `spider --version` fails, the scripts SHALL exit with code 1.
- When `spider doctor` exits non-zero, the scripts SHALL finish the remaining steps and exit with code 10.

#### Scenario: Verification commands
- **WHEN** `sh scripts/install.sh --dry-run` runs with uv 0.12 on PATH
- **THEN** stdout contains the lines `would run: spider --version` and `would run: spider doctor --format table`

#### Scenario: Doctor reports a failure
- **WHEN** `sh scripts/install.sh --no-skill --package <wheel>` runs in a folder whose `spider.toml` contains `[store` and nothing else, so `spider doctor` fails its `workspace` check
- **THEN** the exit code is 10

#### Scenario: Install fails
- **WHEN** `sh scripts/install.sh --no-skill --package <tmp>/missing.whl` runs and that file does not exist
- **THEN** the exit code is 1, and stderr contains a line starting with `error:` followed by a line starting with `hint:`

### Requirement: Offer the Skill to detected agents
Unless `--no-skill` is given, the scripts SHALL detect two agents:
- Claude Code: a `~/.claude` folder, or a `claude` command on PATH
- Codex: a `~/.codex` folder, or a `codex` command on PATH

For each detected agent, they SHALL ask `Install the spider Skill for <Claude Code|Codex>? [Y/n]`, where Enter means yes, and run `spider skill install --target claude` or `--target codex` for each yes. They SHALL read the answer from the terminal (`/dev/tty` in `install.sh`), not from the piped script.

With `--yes`, they SHALL install for every detected agent without asking. When no terminal is available and `--yes` is not given, or when no agent is detected, they SHALL print the `spider skill install` command to run later and not ask.

#### Scenario: Claude Code detected with --yes
- **WHEN** `sh scripts/install.sh --dry-run --yes` runs with a home folder that holds a `.claude` folder and no `.codex` folder, and with no `claude` or `codex` command on PATH
- **THEN** stdout contains the line `would run: spider skill install --target claude` and no line containing `--target codex`

#### Scenario: Codex detected by its folder
- **WHEN** `sh scripts/install.sh --dry-run` runs with a home folder that holds only a `.codex` folder
- **THEN** stdout contains the line `would ask: Install the spider Skill for Codex? [Y/n]`

#### Scenario: --no-skill
- **WHEN** `sh scripts/install.sh --dry-run --yes --no-skill` runs with a home folder that holds a `.claude` folder
- **THEN** stdout contains no line containing `spider skill install`

#### Scenario: No terminal to ask
- **WHEN** `sh scripts/install.sh --package <wheel>` runs without `--yes`, in a new session without a controlling terminal, with a home folder that holds a `.claude` folder
- **THEN** `<home>/.claude/skills/spider` does not exist after the run, and stdout contains `spider skill install --target claude`

#### Scenario: Answer read from the terminal when piped
- **WHEN** on a Linux runner `cat scripts/install.sh | sh -s -- --package <wheel>` runs under a pseudo-terminal that answers `n`, with a home folder that holds a `.claude` folder
- **THEN** `<home>/.claude/skills/spider` does not exist after the run

#### Scenario: Skill installed on a real runner
- **WHEN** `sh scripts/install.sh --yes --package <wheel>` runs with a home folder that holds a `.claude` folder
- **THEN** `<home>/.claude/skills/spider/SKILL.md` exists after the run

### Requirement: PATH setup
When uv's tool bin folder is not on PATH, the scripts SHALL:
- run `uv tool update-shell`, unless `--no-modify-path` is given, so that new terminals find `spider`
- print the one-line command that adds the folder to PATH in the current terminal: `export PATH="<dir>:$PATH"` for POSIX shells, or `$env:Path = "<dir>;$env:Path"` for PowerShell

#### Scenario: PATH update planned
- **WHEN** `sh scripts/install.sh --dry-run` runs with uv 0.12 on PATH and `UV_TOOL_BIN_DIR` set to a folder that is not on PATH
- **THEN** stdout contains the line `would run: uv tool update-shell`

#### Scenario: PATH left alone on request
- **WHEN** the same dry run adds `--no-modify-path`
- **THEN** stdout contains no line `would run: uv tool update-shell`, and it does contain `export PATH=`

#### Scenario: Windows user PATH
- **WHEN** the Windows smoke test runs with the tool bin folder `<home>\.local\bin` not on PATH
- **THEN** after the run, the user-level `Path` environment variable contains `<home>\.local\bin`

### Requirement: No administrator rights
The scripts SHALL never request elevation, so they SHALL contain no `sudo`, no `RunAs` and no UAC prompt. They SHALL change only user-scoped locations:
- folders under the user's home folder: uv, its Python builds and tools, the Skill folders, and shell startup files
- on Windows, the user-level `Path` variable

When `install.sh` runs as root, it SHALL warn on stderr: `warning: running as root; spider will be installed for the root user only`.

#### Scenario: No elevation in the scripts
- **WHEN** the text of `scripts/install.sh` and `scripts/install.ps1` is searched
- **THEN** neither contains `sudo` or `RunAs`

#### Scenario: Root warning
- **WHEN** `sudo -E sh scripts/install.sh --dry-run` runs on a Linux CI runner
- **THEN** stderr contains `warning: running as root; spider will be installed for the root user only`

### Requirement: Output and exit codes
Output SHALL follow these rules:
- Each step SHALL print one line that starts with `==> `.
- An error SHALL go to stderr as a line that starts with `error:`, followed by a line that starts with `hint:`.
- Colour SHALL be used only when stdout is a terminal and `NO_COLOR` is not set.

The installers SHALL use their own exit codes, not the CLI's table:
- 0: installed, and `spider doctor` reported no failed check
- 1: failed (uv, the package, or `spider --version`)
- 2: invalid options
- 10: installed, but `spider doctor` reported a failed check

When a download or install step fails and Codex's `CODEX_SANDBOX_NETWORK_DISABLED` variable is `1`, the hint SHALL explain the fix: approve network access in Codex, or set `network_access = true`. Reading that variable is detection, not a setting.

#### Scenario: Step lines
- **WHEN** `sh scripts/install.sh --no-skill --package <wheel>` runs on a CI runner
- **THEN** stdout contains at least four lines that start with `==> `

#### Scenario: No colour without a terminal
- **WHEN** `sh scripts/install.sh --dry-run` runs with stdout redirected to a file
- **THEN** the file contains no byte 0x1B

#### Scenario: Codex hint on a blocked download
- **WHEN** `sh scripts/install.sh --no-skill --package <tmp>/missing.whl` runs with `CODEX_SANDBOX_NETWORK_DISABLED=1`
- **THEN** the exit code is 1, and stderr contains `network_access = true`

### Requirement: PowerShell sessions stay open
When `install.ps1` runs inside an existing PowerShell session, through `irm … | iex` or a script block, it SHALL NOT close that session, on success or on failure. Instead it SHALL set `$LASTEXITCODE` to its exit code. When run with `-File` or through the documented `powershell -c` one-liner, it SHALL end with that exit code.

#### Scenario: Session survives a dry run
- **WHEN** `& ([scriptblock]::Create((Get-Content -Raw scripts/install.ps1))) -DryRun; Write-Output 'after'` runs in one Windows PowerShell 5.1 session
- **THEN** the last line of output is `after`

#### Scenario: Session survives an invalid option
- **WHEN** `& ([scriptblock]::Create((Get-Content -Raw scripts/install.ps1))) -Bogus; Write-Output "after $LASTEXITCODE"` runs in one Windows PowerShell 5.1 session
- **THEN** the last line of output is `after 2`

#### Scenario: Profile path with a space
- **WHEN** `scripts/install.ps1 -DryRun -Yes` runs on Windows with `USERPROFILE` set to `<tmp>\Test User`, which holds a `.claude` folder, and uv 0.12 on PATH
- **THEN** the exit code is 0, and stdout contains the line `would run: spider skill install --target claude`

### Requirement: Uninstall instructions
`--help` / `-Help` and `docs/installation.md` SHALL explain how to uninstall:
- run `uv tool uninstall spider`
- delete the Skill folders `~/.claude/skills/spider` and `~/.agents/skills/spider`, and any project copies. On Windows these are `%USERPROFILE%\.claude\skills\spider` and `%USERPROFILE%\.agents\skills\spider`.
- Crawl data in `~/.spider/` and in project `.spider/` folders is kept until the user deletes it.
- a link to uv's own uninstall instructions

#### Scenario: sh help
- **WHEN** `sh scripts/install.sh --help` runs
- **THEN** the exit code is 0, and stdout contains `uv tool uninstall spider`, `~/.claude/skills/spider` and `~/.agents/skills/spider`

#### Scenario: PowerShell help
- **WHEN** `scripts/install.ps1 -Help` runs on Windows
- **THEN** stdout contains `uv tool uninstall spider` and `%USERPROFILE%\.claude\skills\spider`

### Requirement: Developer install
`docs/installation.md` SHALL document installing without the scripts. Both forms SHALL pin Python 3.14:
- `uv tool install --python 3.14 spider`
- pipx:
  - `pipx install --python python3.14 spider` on macOS and Linux
  - `pipx install --python 3.14 spider` on Windows, through the `py` launcher

#### Scenario: Developer install documented
- **WHEN** `docs/installation.md` is read
- **THEN** it contains `uv tool install --python 3.14 spider`, `pipx install --python python3.14 spider` and `pipx install --python 3.14 spider`

### Requirement: Hosting
Each GitHub release SHALL carry `install.sh` and `install.ps1` as assets, taken from the tagged commit's `scripts/` folder. As a result:
- `https://github.com/OWNER/REPO/releases/latest/download/install.sh` always serves the latest released script.
- `…/releases/download/v<version>/install.sh` serves a fixed version.

The documented one-liners SHALL use the `latest/download` URLs. The scripts SHALL also be reachable as raw files on the default branch.

#### Scenario: Documented one-liners
- **WHEN** `docs/installation.md` is read
- **THEN** it contains `https://github.com/OWNER/REPO/releases/latest/download/install.sh` and `https://github.com/OWNER/REPO/releases/latest/download/install.ps1`

#### Scenario: Scripts are release assets
- **WHEN** `.github/workflows/release.yml` is parsed
- **THEN** the release job uploads `scripts/install.sh` and `scripts/install.ps1` under the asset names `install.sh` and `install.ps1`

### Requirement: Release gates
`python scripts/release_check.py <tag>` SHALL exit 0 only when all of these hold:
- the tag is `v` followed by the package version
- `scripts/generate_skill.py`, run into a temporary folder, produces files byte-identical to `skills/spider/`, with no extra or missing files
- the `version` in `.claude-plugin/plugin.json` equals the package version

Otherwise it SHALL exit 1 and name each failed gate. When it passes, it SHALL print a JSON object `{"version": <package version>, "prerelease": <true when the version has a PEP 440 pre-release or dev segment>}` on stdout.

#### Scenario: Tag must match the package version
- **WHEN** `python scripts/release_check.py v0.1.0` runs in a checkout whose package version is `0.1.1`
- **THEN** the exit code is 1, and stderr contains `tag v0.1.0 does not match package version 0.1.1`

#### Scenario: Stale Skill copy blocks the release
- **WHEN** `skills/spider/SKILL.md` has one byte changed and `python scripts/release_check.py v<version>` runs
- **THEN** the exit code is 1, and stderr contains `skills/spider/SKILL.md`

#### Scenario: Plugin version must match
- **WHEN** `.claude-plugin/plugin.json` has `version` `0.0.9`, the package version is `0.1.0`, and `python scripts/release_check.py v0.1.0` runs
- **THEN** the exit code is 1, and stderr contains `plugin.json`

#### Scenario: Pre-release detection
- **WHEN** `python scripts/release_check.py v0.2.0rc1` passes in a checkout whose package version is `0.2.0rc1`
- **THEN** stdout is `{"version": "0.2.0rc1", "prerelease": true}`

### Requirement: Release workflow
`.github/workflows/release.yml` SHALL run on pushes of tags that match `v*`, with jobs in this order:

| Job | What it does |
|---|---|
| `verify` | `scripts/release_check.py` and the test suite |
| `build` | `uv build` (wheel and sdist) and a `SHA256SUMS` file |
| `smoke` | the installer smoke tests with the built wheel |
| `publish` | PyPI trusted publishing, in the `pypi` environment with `id-token: write` and no stored API token |
| `release` | a GitHub release with the wheel, the sdist, `install.sh`, `install.ps1` and `SHA256SUMS`, marked as a pre-release when `release_check.py` reports `prerelease: true` |

A failure before `publish` SHALL leave nothing published.

#### Scenario: Tag trigger
- **WHEN** `.github/workflows/release.yml` is parsed
- **THEN** `on.push.tags` is `["v*"]`

#### Scenario: Job order
- **WHEN** the workflow is parsed
- **THEN** `publish` needs `verify`, `build` and `smoke`, and `release` needs `publish`

#### Scenario: Trusted publishing only
- **WHEN** the workflow is parsed
- **THEN** the `publish` job has `permissions.id-token` `write` and `environment` `pypi`, and no step of any job references a secret whose name contains `PYPI`

### Requirement: Installer smoke tests
The `smoke` job SHALL run each install script with `--yes --package <built wheel>` on these runners:
- `ubuntu-latest` (`sh`)
- `macos-latest` (`sh`)
- `windows-latest`, once under Windows PowerShell 5.1 and once under PowerShell 7

On each runner, uv SHALL be absent from PATH, and the home folder SHALL be a new temporary folder that holds a `.claude` folder. On Windows, that folder's path contains a space, and uv's tool, bin, Python and cache folders are set inside it. Each run SHALL check that the script exits with code 0 and that `spider --version` prints the tag's version.

#### Scenario: Fresh Linux
- **WHEN** the smoke job runs `sh scripts/install.sh --yes --package <wheel>` on `ubuntu-latest`
- **THEN** the exit code is 0, and `<home>/.local/bin/spider --version` prints the tag's version

#### Scenario: Fresh macOS
- **WHEN** the smoke job runs `sh scripts/install.sh --yes --package <wheel>` on `macos-latest`
- **THEN** the exit code is 0, and `<home>/.local/bin/spider --version` prints the tag's version

#### Scenario: Fresh Windows PowerShell 5.1
- **WHEN** the smoke job runs `powershell -ExecutionPolicy ByPass -File scripts\install.ps1 -Yes -Package <wheel>` on `windows-latest`, with the home folder `<tmp>\Test User`
- **THEN** the exit code is 0, and `<tmp>\Test User\.local\bin\spider.exe --version` prints the tag's version

#### Scenario: Fresh Windows PowerShell 7
- **WHEN** the smoke job runs `pwsh -File scripts\install.ps1 -Yes -Package <wheel>` on `windows-latest`, with the home folder `<tmp>\Test User`
- **THEN** the exit code is 0, and `<tmp>\Test User\.local\bin\spider.exe --version` prints the tag's version

### Requirement: Supported Python range
The package SHALL declare `requires-python = ">=3.12,<3.15"` and classifiers for Python 3.12, 3.13 and 3.14. Both install scripts SHALL declare the Python version they pass to `--python` as `3.14`. That version SHALL satisfy `requires-python`. `docs/installation.md` SHALL explain two reasons for the pin:
- uv issue #14110
- the missing Python 3.15 wheels for aiohttp, selectolax, msgspec and zstandard

It SHALL also say that the pin will be raised when those wheels ship.

#### Scenario: Pins agree
- **WHEN** `requires-python` from `pyproject.toml` and the Python version declared in both install scripts are read
- **THEN** `requires-python` is `>=3.12,<3.15`, both scripts say `3.14`, and `3.14` satisfies `requires-python`

#### Scenario: Wheel metadata
- **WHEN** the `Requires-Python` field in the `METADATA` of the wheel built by `uv build` is parsed as a specifier set
- **THEN** it equals the specifier set `>=3.12,<3.15`

#### Scenario: Pin explained
- **WHEN** `docs/installation.md` is read
- **THEN** it contains `#14110` and the names aiohttp, selectolax, msgspec and zstandard
