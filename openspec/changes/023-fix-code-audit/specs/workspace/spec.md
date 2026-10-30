## REMOVED Requirements

### Requirement: No environment variables

**Reason:** it said the proxy variables are honoured, which no fetch does; "Environment variables change nothing" replaces it.

**Migration:** none.

## ADDED Requirements

### Requirement: Environment variables change nothing

**In short:** environment variables never select the Workspace, change a setting or change a result.

Environment variables SHALL NOT select the Workspace, SHALL NOT be a source of settings, and SHALL NOT change a Command's behaviour or output. The only inputs are flags and `openlinx.toml`, plus the operating system's own notion of the home folder and the current folder. No environment variable is honoured, so `linx commands` lists none under `environment`. One kind of variable may be read:

- **Detection signals.** Read-only detection signals that host agents set, such as Codex's `CODEX_SANDBOX_NETWORK_DISABLED`, MAY be read to word diagnostics and hints, for example by `linx doctor`. They SHALL NOT change a Command's result, its exit code, the Workspace or any setting.

#### Scenario: A Workspace variable is ignored
- **WHEN** the Workspace is resolved from `H/work/a`, which contains `.openlinx/`, while the environment variables `OPENLINX_WORKSPACE` and `HTTP_PROXY` are set to `H/work/b` and `http://127.0.0.1:3128`
- **THEN** the Workspace root is `H/work/a`

#### Scenario: No environment variable is honoured
- **WHEN** `linx commands` runs
- **THEN** its `environment` list is empty

#### Scenario: Detection signals change nothing
- **WHEN** `linx commands` runs once with the environment variable `CODEX_SANDBOX_NETWORK_DISABLED=1` and once without it
- **THEN** both runs write byte-identical stdout and exit with code 0

#### Scenario: Setting variables are ignored
- **WHEN** the settings of a Workspace without `openlinx.toml` are resolved with the environment variables `OPENLINX_EXAMPLE__LEVEL`, `EXAMPLE__LEVEL` and `LEVEL` all set to `high`
- **THEN** `example.level` is `"low"`

### Requirement: A refused given value names its key

**In short:** a value given with the settings that its setting refuses fails with `invalid_value` and the key, not with an invalid settings file.

A value given with the settings, as a flag, by a caller of a service, or as an override of a continued Crawl, SHALL be checked against its setting like a value of `openlinx.toml`. When the setting refuses it, the call SHALL fail with exit code 2 and the error code `invalid_value`, whose `details.key` is the setting's dotted key. A flag refused by its own bounds or check SHALL give the same `details.key`. The error SHALL NOT name `openlinx.toml`, and a problem of the file itself SHALL still be `settings_invalid`.

#### Scenario: A refused value given with the settings names its key
- **WHEN** the settings of a Workspace without `openlinx.toml` are resolved with the value `"medium"` given for `example.level`
- **THEN** the error has the code `invalid_value`, exit code 2 and `details.key` `"example.level"`, and its details have no `file`

#### Scenario: A refused override of a continued Crawl names its key
- **WHEN** a stopped Crawl is continued with the override `0` for `crawl.concurrency`
- **THEN** the error has the code `invalid_value`, exit code 2 and `details.key` `"crawl.concurrency"`, and the Crawl's file is unchanged

#### Scenario: A refused flag names its setting
- **WHEN** `linx crawl site.test --concurrency 0` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and `details.key` `"crawl.concurrency"`
