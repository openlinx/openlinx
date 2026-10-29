## Purpose

Lets people and agents find out, with one Command, whether OpenLinx can run and crawl on this machine, and how to fix what is wrong.

## ADDED Requirements

### Requirement: Doctor report
`linx doctor [--url <url>] [--proxy <url>]` SHALL run a fixed list of checks. It SHALL print a JSON object with these fields:
- `status`: the worst check status, where `fail` is worse than `warn` and `warn` is worse than `ok`
- `version`: the CLI version
- `counts`: `{"ok": n, "warn": n, "fail": n}`
- `checks`: one entry per check id, in this order: `python`, `package`, `path`, `workspace`, `wal`, `network`, `tls`, `skill.claude`, `skill.codex`, `skill.claude.project`, `skill.codex.project`

Each entry SHALL contain:
- `id`
- `status`: `ok`, `warn` or `fail`
- `message`: one sentence
- `hint`: a concrete next step, or null when there is nothing to do
- `details`: an object with the values the check measured

`--url` SHALL accept only an `http` or `https` URL, and defaults to `https://example.com/`. A usage error SHALL print nothing on stdout.

#### Scenario: Check ids and order
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs while the local fixture site listens on `<port>`
- **THEN** the `id` values of `checks` are, in order, `python`, `package`, `path`, `workspace`, `wal`, `network`, `tls`, `skill.claude`, `skill.codex`, `skill.claude.project`, `skill.codex.project`

#### Scenario: Overall status is the worst check status
- **WHEN** `linx doctor --url http://127.0.0.1:<closed-port>/` runs and nothing listens on `<closed-port>`
- **THEN** the top-level `status` is `"fail"`

#### Scenario: Counts add up
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs against the local fixture site
- **THEN** `counts.ok + counts.warn + counts.fail` equals 11

#### Scenario: Only web URLs are accepted
- **WHEN** `linx doctor --url ftp://example.com/` runs
- **THEN** the Command fails with the CLI's usage error, and stdout is empty

### Requirement: Doctor table output
With `--format table`, `linx doctor` SHALL print one row per check, in the same order as the JSON `checks`. Each row SHALL show the id, the status, the message and the hint.

#### Scenario: One row per check
- **WHEN** `linx doctor --format table --url http://127.0.0.1:<port>/` runs against the local fixture site
- **THEN** stdout contains each of the 11 check ids at the start of a row, in the JSON order

#### Scenario: Non-ASCII path on the Windows console
- **WHEN** on Windows `linx init` has run in the folder `<tmp>\Müller`, and `linx doctor --format table` then runs there as a subprocess whose console code page is 437
- **THEN** stdout, decoded as UTF-8, contains `Müller`

### Requirement: Doctor exit code
`linx doctor` SHALL exit with code 0 when no check has status `fail`, even when some checks warn. A failed check makes the report a partial result under the rule of `010-add-workspace-and-cli-contract`. Doctor SHALL then:
- still print the full report on stdout
- write exactly one error diagnostic to stderr, with `code` `doctor_checks_failed` and a `message` that names the failed check ids
- exit with code 1

#### Scenario: A failed check
- **WHEN** `linx doctor --url http://127.0.0.1:<closed-port>/` runs and nothing listens on `<closed-port>`
- **THEN** the exit code is 1, and stderr holds exactly one error diagnostic, with `code` `"doctor_checks_failed"` and a `message` that contains `network`

#### Scenario: Report still printed on failure
- **WHEN** `linx doctor --url http://127.0.0.1:<closed-port>/` runs and nothing listens on `<closed-port>`
- **THEN** stdout is a JSON report with 11 entries in `checks`

#### Scenario: Warnings keep exit code 0
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs against the local fixture site, over HTTP
- **THEN** the `tls` check has status `"warn"` and the exit code is 0

### Requirement: Doctor leaves no trace
`linx doctor` SHALL leave no file or folder behind. It removes the temporary files it creates to test the Workspace. It SHALL NOT change settings, installed Skills or Crawls. It SHALL open network connections only to the host of the target URL, or to the proxy a Crawl would use.

#### Scenario: Nothing written
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs with the home folder set to the empty temporary folder `<home>` and the current folder set to the empty temporary folder `<cwd>`
- **THEN** both `<home>` and `<cwd>` are still empty after the Command exits

#### Scenario: Connections only to the target
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs against the local fixture site with the network probe recording every address it is asked to connect to
- **THEN** the only address recorded is `127.0.0.1:<port>`

### Requirement: Python check
The `python` check SHALL report the running Python version and interpreter path in `details.version` and `details.executable`. Its status SHALL be `ok` when the version is at least 3.12 and below 3.15, and `fail` otherwise. The hint for `fail` SHALL be `uv tool install --python 3.14 --reinstall openlinx`.

#### Scenario: Supported range
- **WHEN** the `python` check is evaluated for the Python versions `3.11.9`, `3.12.0`, `3.14.2` and `3.15.0`
- **THEN** the statuses are `fail`, `ok`, `ok` and `fail`

#### Scenario: Hint for an unsupported Python
- **WHEN** the `python` check is evaluated for Python `3.15.0`
- **THEN** its hint is `"uv tool install --python 3.14 --reinstall openlinx"`

#### Scenario: The running interpreter
- **WHEN** `linx doctor` runs under the test interpreter
- **THEN** `details.version` of the `python` check equals that interpreter's `platform.python_version()`

### Requirement: Package check
The `package` check SHALL report the installed package version and install location in `details.version` and `details.location`. It SHALL try to import the compiled dependencies that a Crawl needs: at least aiohttp, selectolax, msgspec and zstandard. It SHALL also report the version of the SQLite library that the running Python links, in `details.sqlite_version`: every table of a crawl file is `STRICT`, which SQLite 3.37 or later is needed to create and read. Its status SHALL be `ok` when all of the dependencies import and SQLite is 3.37 or later. Otherwise its status SHALL be `fail`, its message SHALL name each dependency that failed to import, and an older SQLite with its version, and its hint SHALL be `uv tool install --python 3.14 --reinstall openlinx`.

#### Scenario: Version of the installed package
- **WHEN** `linx doctor` runs in the test environment
- **THEN** the `package` check has status `"ok"`, and `details.version` equals the version number printed by `linx --version`

#### Scenario: Missing compiled dependency
- **WHEN** the `package` check is evaluated for import results in which `selectolax` failed with `ImportError: DLL load failed` and the other dependencies imported
- **THEN** its status is `fail` and its message contains `selectolax`

#### Scenario: SQLite version is reported
- **WHEN** `linx doctor` runs in the test environment
- **THEN** `details.sqlite_version` of the `package` check equals the test interpreter's `sqlite3.sqlite_version`

#### Scenario: SQLite older than 3.37
- **WHEN** the `package` check is evaluated with every dependency imported, once for SQLite `3.36.0` and once for SQLite `3.37.0`
- **THEN** the statuses are `fail` and `ok`, and the message of the `fail` contains `SQLite 3.36.0`

### Requirement: PATH check
The `path` check SHALL look up the `linx` command on PATH (`linx.exe` on Windows), run it with `--version`, and report the result in `details.command_path` and `details.command_version`. Its status SHALL be:
- `ok` when the command's version equals the running CLI's version
- `warn` when no `linx` command is on PATH, with the hint `uv tool update-shell`, then open a new terminal
- `warn` when the first `linx` on PATH reports a different version, with a message that names its path and version

#### Scenario: Not on PATH
- **WHEN** `linx doctor` runs with PATH set to an empty temporary folder
- **THEN** the `path` check has status `"warn"` and its hint contains `uv tool update-shell`

#### Scenario: A different linx comes first
- **WHEN** the `path` check is evaluated for a first `linx` on PATH at `/opt/old/bin/linx` that reports `linx 0.0.1`, while the running CLI is `0.2.0`
- **THEN** its status is `warn`, and its message contains `/opt/old/bin/linx` and `0.0.1`

#### Scenario: Windows executable
- **WHEN** on Windows the first folder on PATH holds the `linx.exe` of the running installation
- **THEN** the `path` check has status `"ok"` and `details.command_path` ends with `\linx.exe`

### Requirement: Workspace check
The `workspace` check SHALL find the Workspace the same way other Commands do (`010-add-workspace-and-cli-contract`): the `--workspace` flag, then the nearest folder that holds `.openlinx/` or `openlinx.toml`, then the global Workspace `~/.openlinx/`. It SHALL NOT create the Workspace. Its message SHALL name the Workspace path. It SHALL load the Workspace's settings. It SHALL test that a file can be created and deleted there, or, when the Workspace folder does not exist yet, that the folder could be created.

`details` SHALL include:
- `path`
- `source`, how the Workspace was found: `flag`, `local` or `global`
- `exists`

The status SHALL be `fail`, with the hint to run `linx init` in the project folder or pass `--workspace <folder>`, when either:
- the settings cannot be loaded. The message then includes the settings error.
- the location cannot be written or created.

Otherwise the status SHALL be `ok`.

#### Scenario: Project Workspace
- **WHEN** `linx init` has run in the current folder and then `linx doctor` runs there
- **THEN** the `workspace` check has status `"ok"` and `details.source` `"local"`

#### Scenario: Global Workspace not created yet
- **WHEN** `linx doctor` runs in an empty folder with the home folder set to an empty temporary folder `<home>`
- **THEN** the `workspace` check has status `"ok"`, `details.source` `"global"` and `details.exists` false

#### Scenario: Global Workspace location blocked
- **WHEN** `<home>/.openlinx` is a regular file, not a folder, and `linx doctor` runs in an empty folder
- **THEN** the `workspace` check has status `"fail"` and its hint contains `linx init`

#### Scenario: Invalid settings
- **WHEN** the Workspace's `openlinx.toml` contains the line `this is = = not toml` and `linx doctor` runs
- **THEN** the `workspace` check has status `"fail"` and its message contains `openlinx.toml`

### Requirement: WAL check
The `wal` check SHALL report the journal mode that a new Crawl in the Workspace would use, as `details.journal_mode` (`wal` or `delete`), together with the `store.journal_mode` setting as `details.setting`. It SHALL use the same setting and network-location decision as the crawl store of `015-add-crawl-store`. The status SHALL be:
- `ok` for `wal`.
- `ok` for `delete` when the setting chose it explicitly.
- `warn` when the `auto` setting falls back to `delete` on a network location. The message SHALL say that queries must wait while a Crawl writes. The hint SHALL say to move the Workspace to a local disk with `--workspace` or `linx init`.

#### Scenario: Local disk
- **WHEN** `linx doctor` runs with the Workspace in a local temporary folder
- **THEN** the `wal` check has status `"ok"` and `details.journal_mode` `"wal"`

#### Scenario: Network drive on Windows
- **WHEN** the `wal` check is evaluated for the Windows Workspace folder `\\fileserver\seo\site` with the setting `auto`
- **THEN** its status is `warn` and `details.journal_mode` is `"delete"`

#### Scenario: Rollback journal chosen in the settings
- **WHEN** the Workspace's `openlinx.toml` contains `[store]\njournal_mode = "delete"\n` and `linx doctor` runs on a local disk
- **THEN** the `wal` check has status `"ok"`, `details.journal_mode` `"delete"` and `details.setting` `"delete"`

### Requirement: Network check
The `network` check SHALL use the network probe to resolve the host of the target URL and open a TCP connection to it, or to the proxy that a Crawl would use, within 10 seconds. `details` SHALL include `url`, `elapsed_ms`, `proxy` and, on failure, `error`. The status SHALL be `ok` when the connection opens and `fail` otherwise.

`details.proxy` SHALL be `{source, url}` for the proxy in effect for the target, found as `022-add-fetch-policy` finds it for a Crawl. `source` is one of:
- `flag`: doctor's `--proxy`
- `settings`: the proxy setting in `openlinx.toml`
- `env`: `HTTP_PROXY` or `HTTPS_PROXY` for the target's scheme, when `NO_PROXY` does not exclude the target host
- `none`: no proxy is in effect

`url` is the proxy URL, with any password shown as `***` (`user:***@host`), or null when `source` is `none`.
- A `fail` hint SHALL always include the Codex fix: approve network access for the command, or set `network_access = true` under `[sandbox_workspace_write]` in `~/.codex/config.toml`. It SHALL also give proxy and firewall advice.
- When Codex's own `CODEX_SANDBOX_NETWORK_DISABLED` variable is `1`, or the connection fails with a permission error, the message SHALL say that a sandbox such as Codex's has disabled network access. That variable is a read-only host-agent signal. It is used only to detect the sandbox and choose the hint, and never as a setting.

#### Scenario: Local fixture site reachable
- **WHEN** `linx doctor --url http://127.0.0.1:<port>/` runs while the local fixture site listens on `<port>`
- **THEN** the `network` check has status `"ok"` and `details.url` `"http://127.0.0.1:<port>/"`

#### Scenario: Refused connection
- **WHEN** `linx doctor --url http://127.0.0.1:<closed-port>/` runs and nothing listens on `<closed-port>`
- **THEN** the `network` check has status `"fail"` and its hint contains `network_access = true`

#### Scenario: Codex sandbox
- **WHEN** `linx doctor` runs with `CODEX_SANDBOX_NETWORK_DISABLED=1` and the network probe fails every connection with a permission error
- **THEN** the `network` check has status `"fail"` and its message contains `Codex`

#### Scenario: Default target
- **WHEN** `linx doctor` runs without `--url`, with the network probe accepting the connection
- **THEN** `details.url` of the `network` check is `"https://example.com/"`

#### Scenario: Proxy from the environment is reported and redacted
- **WHEN** `linx doctor --url http://site.test/` runs with `HTTP_PROXY=http://alice:s3cret@proxy.test:3128`, no `NO_PROXY`, no `--proxy`, no proxy in `openlinx.toml`, and a network probe that accepts and records the connection
- **THEN** `details.proxy` of the `network` check is `{"source": "env", "url": "http://alice:***@proxy.test:3128"}`, and the probe recorded only `proxy.test:3128`

### Requirement: TLS check
The `tls` check SHALL use the TLS setup of `022-add-fetch-policy`, the same one that a Crawl uses. It SHALL report in `details.trust_source` which certificates that setup trusts:
- `system`: the operating system's trust store
- `bundled`: the bundled CA certificates, used as a fallback

When the target URL uses `https` and the `network` check passed, it SHALL perform a TLS handshake to the target host with certificate verification. On failure, `details` SHALL include the raw `error` and an `error_kind` of `certificate_verify_failed`, `handshake_failed` or `timeout`, which is the same on every operating system. The status SHALL be:
- `ok` when verification succeeds.
- `fail` when verification fails. The hint SHALL say to add the root certificate of a TLS-inspecting proxy or antivirus to the operating system trust store. On macOS with the `bundled` source, the hint SHALL also mention python.org's `Install Certificates` step.
- `fail` when no trust source can be loaded.
- `warn`, with a message that it was not checked, when the target is not `https` or the `network` check failed.

#### Scenario: Untrusted certificate
- **WHEN** `linx doctor --url https://127.0.0.1:<port>/` targets the HTTPS listener of the fixture site (`022-add-fetch-policy`), whose certificate comes from the fixture's test CA
- **THEN** the `tls` check has status `"fail"` and `details.error_kind` `"certificate_verify_failed"`

#### Scenario: Trusted certificate
- **WHEN** the same listener is checked with the trust-store probe returning a store that contains the fixture's test CA
- **THEN** the `tls` check has status `"ok"`

#### Scenario: Bundled fallback
- **WHEN** the trust-store probe reports that the operating system trust store cannot be loaded, and `linx doctor` runs
- **THEN** `details.trust_source` of the `tls` check is `"bundled"`

#### Scenario: No trust source at all
- **WHEN** the trust-store probe reports that neither the operating system trust store nor the bundled CA certificates can be loaded
- **THEN** the `tls` check has status `"fail"`

#### Scenario: Not checked after a network failure
- **WHEN** `linx doctor --url https://127.0.0.1:<closed-port>/` runs and nothing listens on `<closed-port>`
- **THEN** the `tls` check has status `"warn"` and its message contains `not checked`

### Requirement: Skill checks
The checks `skill.claude`, `skill.codex`, `skill.claude.project` and `skill.codex.project` SHALL each inspect one install location of `linx skill install`. Project locations are relative to the current folder. Each SHALL report `details.path`, `details.installed_version` (or null) and `details.cli_version`. The status SHALL be:
- `ok`, with the message `not installed` and the matching `linx skill install` command as the hint, when there is no Skill at that location.
- `ok` when the Skill's stamped version equals the CLI version.
- `warn`, with the matching `linx skill install` command as the hint, when the stamped version is older.
- `warn`, with the hint `uv tool upgrade openlinx`, when the stamped version is newer.
- `warn`, with the matching command plus `--force` as the hint, when a `SKILL.md` exists without a linx stamp.

#### Scenario: Not installed
- **WHEN** `linx doctor` runs with the home folder and the current folder both empty
- **THEN** all four Skill checks have status `"ok"` and `details.installed_version` null

#### Scenario: Outdated Codex Skill
- **WHEN** `<home>/.agents/skills/openlinx/SKILL.md` is stamped `0.0.1` and `linx doctor` runs
- **THEN** the `skill.codex` check has status `"warn"` and hint `"linx skill install --target codex"`

#### Scenario: Skill newer than the CLI
- **WHEN** `<home>/.claude/skills/openlinx/SKILL.md` is stamped `999.0.0` and `linx doctor` runs
- **THEN** the `skill.claude` check has status `"warn"` and hint `"uv tool upgrade openlinx"`

#### Scenario: Hand-made project Skill
- **WHEN** `.claude/skills/openlinx/SKILL.md` in the current folder has no linx stamp and `linx doctor` runs
- **THEN** the `skill.claude.project` check has status `"warn"` and hint `"linx skill install --target claude --project --force"`

#### Scenario: Current Skill
- **WHEN** `linx skill install --target claude` has run and then `linx doctor` runs
- **THEN** the `skill.claude` check has status `"ok"` and `details.installed_version` equals `details.cli_version`
