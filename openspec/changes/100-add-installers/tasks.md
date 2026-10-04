> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Every task is one red → green slice and one commit whose message names its scenario:
1. Write the failing test at the named seam (docs/testing.md) and watch it fail for the right reason.
2. Write only enough code to make it pass.
3. Run the full suite.

Installer tests live in `tests/install/` and run in the CI install job on Windows, macOS and Linux. Each run uses:
- the real scripts
- real uv, either absent from PATH or installed
- a wheel built from the checkout (`<wheel>`), passed with `--package`
- a new temporary home folder, with uv's folders inside it

Our CLI is never replaced, and no fake `claude` or `codex` program is used: agents are detected by their folders.

## 1. `install.sh` options and dry-run plan

- [ ] 1.1 Drive "Unknown option in sh" (install-and-packaging seam). Build the harness:
  - a session-scoped `<wheel>` built with `uv build`
  - the temporary home folder
  - PATH with and without uv

  Then write a POSIX `sh` skeleton with option parsing, a usage line and exit code 2.
- [ ] 1.2 Drive "sh help" (install-and-packaging seam), including the uninstall steps.
- [ ] 1.3 Drive "First install plan" (install-and-packaging seam) with the `--dry-run` plan printer and the `PYTHON_VERSION=3.14` constant.
- [ ] 1.4 Drive "Dry run changes nothing" (install-and-packaging seam).
- [ ] 1.5 Drive "uv missing on macOS or Linux" (install-and-packaging seam). Look for uv on PATH, then in `$UV_INSTALL_DIR` and `$XDG_BIN_HOME`, then in `~/.local/bin`, and plan the curl installer with a wget fallback.
- [ ] 1.6 Drive "uv too old" (install-and-packaging seam, with uv 0.8.0 installed from PyPI into a temporary folder), using the minimum-version constant 0.9.0.
- [ ] 1.7 Drive "Package spec" (install-and-packaging seam).
- [ ] 1.8 Drive "Verification commands" (install-and-packaging seam).
- [ ] 1.9 Drive "PATH update planned" (install-and-packaging seam).
- [ ] 1.10 Drive "PATH left alone on request" (install-and-packaging seam).
- [ ] 1.11 Drive "Claude Code detected with --yes" (install-and-packaging seam).
- [ ] 1.12 Drive "Codex detected by its folder" (install-and-packaging seam).
- [ ] 1.13 Drive "--no-skill" (install-and-packaging seam).
- [ ] 1.14 Drive "No colour without a terminal" (install-and-packaging seam).
- [ ] 1.15 Docs: write the macOS/Linux section of `docs/installation.md`, with the one-liner, `sh -s -- <options>` and every option.
- [ ] 1.16 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. `install.sh` real runs

- [ ] 2.1 Drive "Successful install" (install-and-packaging seam) by executing the plan.
- [ ] 2.2 Drive "Step lines" (install-and-packaging seam).
- [ ] 2.3 Drive "Install fails" (install-and-packaging seam, with a wheel path that does not exist): `error:` and `hint:` on stderr, and exit code 1.
- [ ] 2.4 Drive "Codex hint on a blocked download" (install-and-packaging seam).
- [ ] 2.5 Drive "Doctor reports a failure" (install-and-packaging seam, run in a folder with an invalid `spider.toml`): exit code 10 once the remaining steps have run.
- [ ] 2.6 Drive "Upgrade plan" (install-and-packaging seam, after installing `<wheel>`).
- [ ] 2.7 Drive "Upgrade reported" (install-and-packaging seam, with a second wheel built from a temporary copy of the checkout with the version set to `0.0.1`).
- [ ] 2.8 Drive "Already up to date" (install-and-packaging seam).
- [ ] 2.9 Drive "Skill installed on a real runner" (install-and-packaging seam).
- [ ] 2.10 Drive "No terminal to ask" (install-and-packaging seam, in a new session without a controlling terminal).
- [ ] 2.11 Drive "Answer read from the terminal when piped" (install-and-packaging seam, on Linux under `script`, with the answer `n`).
- [ ] 2.12 Drive "uv installed into the home folder" (install-and-packaging seam).
- [ ] 2.13 Drive "Root warning" (install-and-packaging seam, on Linux with `sudo -E`).
- [ ] 2.14 Drive "No elevation in the scripts" (install-and-packaging seam) with a static text test over both scripts. Add `shellcheck -s sh` to CI.
- [ ] 2.15 Docs: add "What the installer changes on your machine", "Exit codes" (0, 1, 2, 10) and "Uninstall" to `docs/installation.md`.
- [ ] 2.16 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. `install.ps1`

- [ ] 3.1 Drive "Unknown option in PowerShell" (install-and-packaging seam, under `powershell` 5.1 and `pwsh` 7). Write a script skeleton with plain switches, leftover arguments in `$args`, usage on stderr and exit code 2.
- [ ] 3.2 Drive "Session survives a dry run" (install-and-packaging seam). Call `exit` only when `$PSCommandPath` is set. Otherwise set `$global:LASTEXITCODE` and return.
- [ ] 3.3 Drive "Session survives an invalid option" (install-and-packaging seam).
- [ ] 3.4 Drive "PowerShell help" (install-and-packaging seam).
- [ ] 3.5 Drive "uv missing on Windows" (install-and-packaging seam), with TLS 1.2 or higher for downloads.
- [ ] 3.6 Drive "Profile path with a space" (install-and-packaging seam), including agent detection under `USERPROFILE`, and `Read-Host` only in an interactive, non-redirected host.
- [ ] 3.7 Drive the Windows run of "First install plan" (install-and-packaging seam), with the test parametrised over both scripts.
- [ ] 3.8 Drive the Windows run of "Package spec" (install-and-packaging seam).
- [ ] 3.9 Drive the Windows run of "Successful install" (install-and-packaging seam). Save and restore `[Console]::OutputEncoding` around the `spider` calls.
- [ ] 3.10 Drive the Windows run of "Install fails" (install-and-packaging seam).
- [ ] 3.11 Drive the Windows run of "Doctor reports a failure" (install-and-packaging seam).
- [ ] 3.12 Drive the Windows run of "Codex hint on a blocked download" (install-and-packaging seam).
- [ ] 3.13 Drive "Windows user PATH" (install-and-packaging seam). Add PSScriptAnalyzer to CI.
- [ ] 3.14 Docs: add the Windows section to `docs/installation.md`, with the one-liner and the script-block form for passing options.
- [ ] 3.15 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Python pin, developer install and hosting docs

- [ ] 4.1 Drive "Pins agree" (install-and-packaging seam). Compare `requires-python`, which `000-scaffold-project` already sets, with both scripts' constants, and add the Python 3.12–3.14 classifiers to `pyproject.toml`.
- [ ] 4.2 Drive "Wheel metadata" (install-and-packaging seam) by parsing `Requires-Python` from `<wheel>`.
- [ ] 4.3 Drive "Pin explained" (install-and-packaging seam) by writing "Why Python 3.14" in `docs/installation.md`: uv #14110, the missing 3.15 wheels, and when the pin moves.
- [ ] 4.4 Drive "Developer install documented" (install-and-packaging seam) by writing the `uv tool install` and `pipx` instructions.
- [ ] 4.5 Drive "Documented one-liners" (install-and-packaging seam). The URLs must be the ones that `080-add-agent-skill` quotes.
- [ ] 4.6 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Release gates and workflow structure

- [ ] 5.1 Drive "Tag must match the package version" (install-and-packaging seam, running `scripts/release_check.py` against a temporary copy of the checkout).
- [ ] 5.2 Drive "Stale Skill copy blocks the release" (install-and-packaging seam). Run `scripts/generate_skill.py` from `080-add-agent-skill` into a temporary folder and compare it byte for byte with `skills/spider/`.
- [ ] 5.3 Drive "Plugin version must match" (install-and-packaging seam).
- [ ] 5.4 Drive "Pre-release detection" (install-and-packaging seam), with the JSON result on stdout.
- [ ] 5.5 Drive "Tag trigger" (install-and-packaging seam) with a first `.github/workflows/release.yml`.
- [ ] 5.6 Drive "Job order" (install-and-packaging seam). Add the `verify`, `build`, `smoke`, `publish` and `release` jobs. The `build` job runs `uv build` and writes `SHA256SUMS`.
- [ ] 5.7 Drive "Trusted publishing only" (install-and-packaging seam), with `pypa/gh-action-pypi-publish`, environment `pypi` and `id-token: write`.
- [ ] 5.8 Drive "Scripts are release assets" (install-and-packaging seam). The `release` job uses `gh release create`, adding `--prerelease` from the gate output.
- [ ] 5.9 Docs: write `RELEASING.md`:
  - the release-commit steps: bump the version, run `scripts/generate_skill.py skills/spider`, bump `plugin.json`
  - tagging
  - the trusted-publisher setup, with the placeholder project name
- [ ] 5.10 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Smoke tests in the release workflow

- [ ] 6.1 Drive "Fresh Linux" (install-and-packaging seam) in the `smoke` job, with a new home folder that holds `.claude`, uv removed from PATH, and the built wheel.
- [ ] 6.2 Drive "Fresh macOS" (install-and-packaging seam).
- [ ] 6.3 Drive "Fresh Windows PowerShell 5.1" (install-and-packaging seam), with the home folder `<tmp>\Test User` and every `UV_*` folder inside it.
- [ ] 6.4 Drive "Fresh Windows PowerShell 7" (install-and-packaging seam).
- [ ] 6.5 Run the CI install job, which covers the tests of groups 1–4, on pull requests that touch `scripts/install.*` or `tests/install/`. Check it with a pull request that breaks the wheel on purpose: the job must go red.
- [ ] 6.6 Docs: add troubleshooting to `docs/installation.md`: PATH in new terminals and GUI apps, proxies and TLS inspection, Codex network approval, and exit code 10.
- [ ] 6.7 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Publishing rehearsal and post-release check

- [ ] 7.1 Add a `workflow_dispatch` input that points `publish` at TestPyPI. Rehearse from a fork with tag `v0.0.1rc1`, and record the run links in the PR:
  - `verify`, `build` and `smoke` pass.
  - The package appears on TestPyPI without a stored token.
  - A GitHub pre-release carries the five assets.
- [ ] 7.2 Add the non-blocking `post-release check` job, which runs the real `latest/download` one-liners with `--yes --no-skill` on the three OSes. Check it against the rehearsal release.
- [ ] 7.3 Docs: add the rehearsal procedure and how to read the post-release check to `RELEASING.md`.
- [ ] 7.4 Review: run the code-review skill on group 7's commits and on the whole change, then refactor with the whole suite green.
