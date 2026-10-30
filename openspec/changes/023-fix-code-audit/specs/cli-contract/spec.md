## MODIFIED Requirements

### Requirement: Self-description with linx commands

**In short:** `linx commands` describes every Command, exit code, diagnostic and honoured environment variable in one JSON document, the same on every OS.

`linx commands` SHALL return one JSON document with these keys:

| Key | Content |
|---|---|
| `tool` | `name` and `version` |
| `commands` | every Command that `--help` shows, including `commands` itself, sorted by name |
| `exit_codes` | `code`, `name` and `description` of each exit code |
| `diagnostics` | every diagnostic code, with `level`, `exit_code` (null for warnings and info) and `description` |
| `environment` | the environment variables the tool honours, as entries with `names` (matched in any letter case) and `description`; empty, as the workspace capability says |

A Command's name is its full path, for example `crawls list`. Each Command entry SHALL have:
- `name`, `summary` and `description`
- `output`: `document`, `list` or `rows`
- `events`: `true` when the Command reports progress events
- `formats`
- `arguments`: each with `name`, `type`, `required`, `variadic`, `default` and `description`
- `options`: each with `name`, `short`, `type`, `choices`, `default`, `min` and `max` (the bounds of a number, or null), `required`, `multiple`, `global`, `setting` (its `openlinx.toml` key, or null), `secret` and `description`; a hidden option SHALL NOT be listed
- `fields`: `{available, default}` for list and rows Commands, otherwise null
- `examples`

The output SHALL be identical on every OS for the same version, and SHALL NOT need a Workspace.

The description SHALL be consistent, and the tool SHALL refuse to start with a Command that would break this:
- the default of a Command's `--format` is the first of its `formats`
- the default fields of a Command are all among its available fields

An option whose `setting` is not null SHALL take `secret` from that setting, so a secret setting and its flag are never described differently. An option without a setting SHALL declare `secret` itself.

#### Scenario: Default format comes first
- **WHEN** the tool is built with a document Command whose formats are `json` and `table`, and whose `--format` defaults to `table`
- **THEN** building the tool fails, naming that Command

#### Scenario: Default fields are available
- **WHEN** the tool is built with a list Command whose available fields are `n` and `sq`, and whose default fields are `n` and `size`
- **THEN** building the tool fails, naming that Command

#### Scenario: A secret option inherits from its setting
- **WHEN** `linx commands` runs in a tool that includes the example settings Command, whose `--level` maps to `example.level` and whose `--token` maps to the secret setting `example.token`
- **THEN** its `--token` option has `"setting":"example.token"` and `"secret":true`, and its `--level` option has `"setting":"example.level"` and `"secret":false`

#### Scenario: A secret option without a setting
- **WHEN** `linx commands` runs in a tool that includes the example settings Command, whose `--api-key` maps to no setting and is declared secret
- **THEN** its `--api-key` option has `"setting":null` and `"secret":true`

#### Scenario: The Command lists itself
- **WHEN** `linx commands` runs
- **THEN** `commands` has an entry with `"name":"commands"`

#### Scenario: Entry of a document Command
- **WHEN** `linx commands` runs
- **THEN** the `init` entry has `"output":"document"`, `"events":false`, `"formats":["json","table"]` and `"fields":null`

#### Scenario: Entry of a list Command
- **WHEN** `linx commands` runs in a tool that includes the example list Command
- **THEN** its entry has `"output":"list"`, `"formats":["json","jsonl","table"]` and `"fields":{"available":["n","sq"],"default":["n"]}`

#### Scenario: Option details
- **WHEN** `linx commands` runs
- **THEN** the `--workspace` option of the `init` entry has `"type":"path"`, `"default":null`, `"global":true`, `"setting":null` and `"secret":false`

#### Scenario: Tool version
- **WHEN** `linx commands` runs
- **THEN** `tool` is `{"name":"openlinx","version":V}`, where V is the `version` in `pyproject.toml`

#### Scenario: Same description on every OS
- **WHEN** `linx commands` runs on Windows, macOS and Linux
- **THEN** the entry for `init` is byte-identical on all three

#### Scenario: Bounds of an option
- **WHEN** `linx commands` runs
- **THEN** the `--concurrency` option of the `crawl` entry has `"min":1` and `"max":50`, and its `--rate` option has `"min":null` and `"max":null`

#### Scenario: A hidden option is not described
- **WHEN** `linx commands` runs in a tool that includes the example settings Command with a hidden option `--internal-flag`
- **THEN** no option of its entry has `"name":"--internal-flag"`
