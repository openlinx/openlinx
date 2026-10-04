# workspace Specification

## Purpose

Defines where a Workspace keeps its Crawls and settings, how every Command finds the Workspace, how `spider init` creates one, and how `spider.toml` settings combine with flags and defaults.

Conventions used in the scenarios:
- `H` is the absolute path of the home folder.
- Paths are written with `/`, and Windows uses `\`.
- Settings scenarios use `example.level`, a setting with the allowed values `"low"` and `"high"` and the default `"low"`. It stands in for the settings tables that later changes register, such as `[store]` from `015-add-crawl-store`.
- `example.token` is a secret string setting that is unset by default. It stands in for settings such as `022`'s proxy.
- `groups` is a keyed table: its entries are named by the user, and each has a `level` like `example.level`. It stands in for `040`'s `[rules.<id>]`.

## Requirements

### Requirement: Workspace layout

A local Workspace SHALL be a folder, its root, that contains a `.spider/` data folder, a `spider.toml` settings file, or both. Its Crawls SHALL be stored in `<root>/.spider/crawls/`, and its settings SHALL be read from `<root>/spider.toml`.

The global Workspace SHALL keep its Crawls in `H/.spider/crawls/` and read its settings from `H/.spider/spider.toml`.

Every data folder SHALL contain a `.gitignore` file whose content is exactly `# Created by spider: crawl data is not committed.\n*\n`.

#### Scenario: Files of a new local Workspace
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** exactly these entries exist under `H/work/shop`: `.spider/`, `.spider/.gitignore`, `.spider/crawls/` and `spider.toml`

#### Scenario: Data folder ignores its own contents
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/.spider/.gitignore` contains exactly `# Created by spider: crawl data is not committed.\n*\n`

#### Scenario: Location of the global Workspace
- **WHEN** the global Workspace is resolved
- **THEN** its data folder is `H/.spider` and its settings file is `H/.spider/spider.toml`

### Requirement: Finding the Workspace

A Command that uses a Workspace SHALL take the first of these that applies:
1. the folder given with `--workspace`
2. the nearest folder that contains `.spider/` or `spider.toml`, searching the current folder and then each parent in turn
3. the global Workspace

The search SHALL stop at the home folder. A search that reaches the home folder SHALL select the global Workspace.

The home folder is never a local Workspace. `--workspace` naming the home folder SHALL select the global Workspace, whose settings file is `H/.spider/spider.toml`. A file `H/spider.toml` SHALL never be read.

When the `--workspace` folder does not exist, the Command SHALL fail with the error code `workspace_not_found`. `spider init` is the exception: it creates the folder.

#### Scenario: The flag wins
- **WHEN** the current folder is `H/work/a`, which contains `.spider/`, and the Workspace is resolved with `--workspace H/work/b`
- **THEN** the Workspace root is `H/work/b`

#### Scenario: Workspace in the current folder
- **WHEN** the Workspace is resolved from the current folder `H/work/shop`, which contains `.spider/`
- **THEN** the Workspace root is `H/work/shop`

#### Scenario: Workspace in a parent folder
- **WHEN** the Workspace is resolved from `H/work/shop/blog`, and only `H/work/shop` contains `.spider/`
- **THEN** the Workspace root is `H/work/shop`

#### Scenario: A settings file alone marks a Workspace
- **WHEN** the Workspace is resolved from `H/work/shop/blog`, and `H/work/shop` contains `spider.toml` but no `.spider/`
- **THEN** the Workspace root is `H/work/shop`

#### Scenario: The nearest Workspace wins
- **WHEN** the Workspace is resolved from `H/work/shop/blog`, and both `H/work` and `H/work/shop` contain `.spider/`
- **THEN** the Workspace root is `H/work/shop`

#### Scenario: Fallback to the global Workspace
- **WHEN** the Workspace is resolved from `H/work/notes`, and no folder from `H/work/notes` up to `H` contains `.spider/` or `spider.toml`
- **THEN** the global Workspace is selected, with the data folder `H/.spider`

#### Scenario: The home folder is the global Workspace
- **WHEN** the Workspace is resolved from the current folder `H`, which contains `.spider/`
- **THEN** the global Workspace is selected, with the settings file `H/.spider/spider.toml`

#### Scenario: The home folder given with --workspace
- **WHEN** the Workspace is resolved from `H/work/a` with `--workspace H`
- **THEN** the global Workspace is selected, with the settings file `H/.spider/spider.toml`

#### Scenario: A settings file in the home folder is not read
- **WHEN** the settings are resolved from `H/work/notes`, which is not a Workspace, while `H/spider.toml` contains `[example]\nlevel = "high"\n` and `H/.spider/spider.toml` does not exist
- **THEN** `example.level` is `"low"`

#### Scenario: Missing --workspace folder
- **WHEN** the Workspace is resolved with `--workspace H/missing`, and `H/missing` does not exist
- **THEN** resolution fails with the error code `workspace_not_found`

#### Scenario: Forward slashes on Windows
- **WHEN** on Windows the Workspace is resolved with `--workspace` written as `H/work/b`, using `/` separators
- **THEN** the Workspace root is the folder `H\work\b`

#### Scenario: Home folder with non-ASCII characters on Windows
- **WHEN** on Windows the home folder `H` is a folder named `Пользователь`, and the Workspace is resolved from `H\notes`, which is not a Workspace
- **THEN** the data folder of the selected global Workspace is `H\.spider`

### Requirement: No environment variables

Environment variables SHALL NOT select the Workspace, SHALL NOT be a source of settings, and SHALL NOT change a Command's behaviour or output. The only inputs are flags and `spider.toml`, plus the operating system's own notion of the home folder and the current folder. There are two exceptions:

- **Proxy variables.** The standard proxy variables `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY`, in any letter case, SHALL be honoured for fetching. `--proxy` or `[crawl] proxy` overrides them, and `022-add-fetch-policy` owns this behaviour. They are the only variables that `spider commands` lists under `environment`.
- **Detection signals.** Read-only detection signals that host agents set, such as Codex's `CODEX_SANDBOX_NETWORK_DISABLED`, MAY be read to word diagnostics and hints, for example by `spider doctor`. They SHALL NOT change a Command's result, its exit code, the Workspace or any setting.

#### Scenario: A Workspace variable is ignored
- **WHEN** the Workspace is resolved from `H/work/a`, which contains `.spider/`, while the environment variables `SPIDER_WORKSPACE` and `HTTP_PROXY` are set to `H/work/b` and `http://127.0.0.1:3128`
- **THEN** the Workspace root is `H/work/a`

#### Scenario: The proxy variables are the one exception
- **WHEN** `spider commands` runs
- **THEN** its `environment` list holds exactly one entry, whose `names` are `["HTTP_PROXY","HTTPS_PROXY","NO_PROXY"]`, and no entry names `SPIDER_WORKSPACE`

#### Scenario: Detection signals change nothing
- **WHEN** `spider commands` runs once with the environment variable `CODEX_SANDBOX_NETWORK_DISABLED=1` and once without it
- **THEN** both runs write byte-identical stdout and exit with code 0

#### Scenario: Setting variables are ignored
- **WHEN** the settings of a Workspace without `spider.toml` are resolved with the environment variables `SPIDER_EXAMPLE__LEVEL`, `EXAMPLE__LEVEL` and `LEVEL` all set to `high`
- **THEN** `example.level` is `"low"`

### Requirement: Initialising a Workspace with spider init

`spider init` SHALL make its target folder a local Workspace. The target is the current folder, or the folder given with `--workspace`; `spider init` creates that folder and any missing parents.

It SHALL create only what is missing and SHALL never modify an existing file.

Its JSON result SHALL have the keys `workspace`, `data_dir`, `settings_file`, `global` and `created`, in that order:
- the first three are absolute paths
- `global` is `true` only when the target is the home folder
- `created` lists the paths this run created, in the order `.spider`, `.spider/.gitignore`, `.spider/crawls`, `spider.toml`

When a folder above the target, below the home folder, is already a local Workspace, `spider init` SHALL still succeed. It SHALL also write the warning `workspace_nested`, whose `details.parent` is that Workspace's root.

When the target or its data folder cannot be created or written, `spider init` SHALL fail with the error code `workspace_not_writable`, whose message names the folder.

#### Scenario: First run
- **WHEN** `spider init` runs in the empty current folder `H/work/shop`
- **THEN** the exit code is 0, and stdout is the JSON object `{"workspace":"H/work/shop","data_dir":"H/work/shop/.spider","settings_file":"H/work/shop/spider.toml","global":false,"created":["H/work/shop/.spider","H/work/shop/.spider/.gitignore","H/work/shop/.spider/crawls","H/work/shop/spider.toml"]}`

#### Scenario: Second run creates nothing
- **WHEN** `spider init` runs twice in `H/work/shop`
- **THEN** the second run exits 0 with `"created":[]`

#### Scenario: Existing settings file is kept byte for byte
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains exactly `[example]\nlevel = "high"\n`
- **THEN** `H/work/shop/spider.toml` still contains exactly `[example]\nlevel = "high"\n`

#### Scenario: Target folder is created
- **WHEN** `spider init --workspace H/work/new/site` runs, and `H/work/new` does not exist
- **THEN** the exit code is 0, and `H/work/new/site/.spider/crawls` exists

#### Scenario: Initialising the home folder
- **WHEN** `spider init` runs in the current folder `H`
- **THEN** the result has `"global":true` and `"settings_file":"H/.spider/spider.toml"`

#### Scenario: Nested Workspace warning
- **WHEN** `spider init` runs in `H/work/shop/blog`, and `H/work/shop` contains `.spider/`
- **THEN** the exit code is 0, and stderr has one line with `"level":"warning"`, `"code":"workspace_nested"` and `"details":{"parent":"H/work/shop"}`

#### Scenario: Unwritable target folder
- **WHEN** `spider init --workspace H/work/notes.txt/site` runs, and `H/work/notes.txt` is a file
- **THEN** the exit code is 7, and the error has the code `workspace_not_writable`

### Requirement: Initialising without the CLI

What `spider init` does SHALL be available as a service call that takes typed inputs and a reporter for warnings and events, and returns the same result as the Command's JSON. A caller other than the CLI, such as the MCP server of `090-add-mcp-server`, SHALL get the same files, result and diagnostics.

#### Scenario: Initialising without the CLI
- **WHEN** the Workspace service initialises `H/work/shop/blog` with a reporter that collects what it is given, and `H/work/shop` contains `.spider/`
- **THEN** the result's `created` lists the four created paths, and the reporter holds exactly one warning, `workspace_nested`, whose `details.parent` is `H/work/shop`

### Requirement: Commented settings template

The `spider.toml` written by `spider init` SHALL be valid TOML that sets no value. It SHALL start with a comment that names the precedence (flag, then `spider.toml`, then default). For every setting the tool knows, it SHALL contain:
- the setting's table header, uncommented
- a comment describing the setting
- the commented-out line `# <key> = <default>`, or `# <key> =` for a setting that is unset by default

A keyed table SHALL appear as a comment describing it and the commented-out header `# [<table>.<name>]`, followed by the commented-out lines of an entry's settings.

Loading this file SHALL give the same settings as having no settings file.

#### Scenario: A setting in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains the line `[example]`, followed later by the line `# level = "low"`

#### Scenario: An unset setting in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains the line `[example]`, followed later by the line `# token =`

#### Scenario: A keyed table in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains the line `# [groups.<name>]`, followed later by the line `# level = "low"`

#### Scenario: Template loads as defaults
- **WHEN** the settings of `H/work/shop` are resolved right after `spider init` created its `spider.toml`
- **THEN** they are equal to the settings resolved for the Workspace `H/work/empty`, which has `.spider/` but no `spider.toml`

### Requirement: Settings precedence

Settings SHALL be grouped in `spider.toml` tables that each change registers. A keyed table SHALL hold entries named by the user, each written `[<table>.<name>]` with the same settings. Each setting SHALL take its value from the first source that sets it:
1. its Command flag
2. `spider.toml`
3. its default

A setting that mirrors a flag SHALL live in a table the Command reads, usually named after it. Its key SHALL be the flag's long name without the leading dashes, with `-` replaced by `_`.

`--format`, `--fields`, `--limit`, `--cursor`, `--crawl` and `--workspace` SHALL have no `spider.toml` key.

#### Scenario: Default
- **WHEN** the settings of a Workspace without `spider.toml` are resolved
- **THEN** `example.level` is `"low"`

#### Scenario: Settings file over default
- **WHEN** the settings are resolved from a `spider.toml` that contains `[example]\nlevel = "high"\n`
- **THEN** `example.level` is `"high"`

#### Scenario: Flag over settings file
- **WHEN** the settings are resolved from a `spider.toml` that contains `[example]\nlevel = "high"\n`, with the flag value `"low"` given for `example.level`
- **THEN** `example.level` is `"low"`

#### Scenario: Named entries
- **WHEN** the settings are resolved from a `spider.toml` that contains `[groups.blog]\nlevel = "high"\n`
- **THEN** `groups.blog.level` is `"high"`

#### Scenario: Output flags have no settings key
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[output]\nformat = "table"\n`
- **THEN** the exit code is 3, and the error has the code `settings_invalid` and `details.errors[0].key` `"output"`

### Requirement: Invalid settings name the offending key

`spider.toml` SHALL be checked completely whenever settings load, including every table that a later change registers. When it is invalid, a Command that loads it SHALL fail and do nothing else. It SHALL exit with code 3 and the error code `settings_invalid`, whose details are:
- `details.file`: the file's absolute path
- `details.errors`: every problem as `{key, message}`, in file order
  - `key` is the dotted key, or `null` for a TOML syntax error
  - a syntax error also carries `line`

Unknown tables and keys SHALL be problems. The error's hint SHALL name the closest known key when one exists.

`spider init` SHALL validate an existing `spider.toml` before creating anything. Commands that do not use a Workspace, such as `spider commands`, SHALL NOT read `spider.toml`.

#### Scenario: Invalid value
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[example]\nlevel = "medium"\n`
- **THEN** the exit code is 3, and `details.errors[0].key` is `"example.level"`

#### Scenario: Unknown key with a suggestion
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[example]\nlevl = "high"\n`
- **THEN** `details.errors[0].key` is `"example.levl"`, and the hint contains `level`

#### Scenario: Unknown key in a named entry
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[groups.blog]\nlevl = "high"\n`
- **THEN** `details.errors[0].key` is `"groups.blog.levl"`, and the hint contains `level`

#### Scenario: TOML syntax error
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[example\n`
- **THEN** `details.errors[0]` has `"key":null` and `"line":1`

#### Scenario: Every problem is listed
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[example]\nlevel = 1\n[crawler]\n`
- **THEN** the keys in `details.errors` are `"example.level"` and `"crawler"`, in that order

#### Scenario: Nothing is created when the settings are invalid
- **WHEN** `spider init` runs in `H/work/shop`, which has no `.spider/` and whose `spider.toml` contains `[example\n`
- **THEN** `H/work/shop/.spider` does not exist afterwards

#### Scenario: Commands without a Workspace ignore the settings file
- **WHEN** `spider commands` runs in `H/work/shop`, whose `spider.toml` contains `[example\n`
- **THEN** the exit code is 0
