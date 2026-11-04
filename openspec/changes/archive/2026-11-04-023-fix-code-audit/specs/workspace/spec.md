## ADDED Requirements

### Requirement: A refused given value names its key

**In short:** a value given with the settings that its setting refuses fails with `invalid_value` and the key, not with an invalid settings file.

A value given with the settings, as a flag, by a caller of a service, or as an override of a continued Crawl, SHALL be checked against its setting like a value of `openlinx.toml`. When the setting refuses it, the call SHALL fail with exit code 2 and the error code `invalid_value`, whose `details.key` is the setting's dotted key. A table given with the settings that is not registered SHALL fail the same way, with the table's name as `details.key`. A flag refused by its own bounds or check SHALL give the same `details.key`. The error SHALL NOT name `openlinx.toml`, and a problem of the file itself SHALL still be `settings_invalid`. When a given value and a value of `openlinx.toml` are both refused, the error SHALL be the given value's.

#### Scenario: A refused value given with the settings names its key
- **WHEN** the settings of a Workspace without `openlinx.toml` are resolved with the value `"medium"` given for `example.level`
- **THEN** the error has the code `invalid_value`, exit code 2 and `details.key` `"example.level"`, and its details have no `file`

#### Scenario: A refused given value is reported before a refused file value
- **WHEN** the settings of a Workspace whose `openlinx.toml` sets `example.level` to `"medium"` are resolved with the value `0` given for `crawl.concurrency`
- **THEN** the error has the code `invalid_value` and `details.key` `"crawl.concurrency"`

#### Scenario: A refused file value beside a given value stays a settings file error
- **WHEN** the settings of a Workspace whose `openlinx.toml` sets `crawl.max_depth` to `-1` are resolved with the value `5` given for `crawl.concurrency`
- **THEN** the error has the code `settings_invalid`, exit code 3 and `details.file`, and its error lists the key `crawl.max_depth`

#### Scenario: A table given with the settings that is not registered names it
- **WHEN** the settings of a Workspace without `openlinx.toml` are resolved with a value given for `crawl_rules.level`, and no table `crawl_rules` is registered
- **THEN** the error has the code `invalid_value`, exit code 2 and `details.key` `"crawl_rules"`, and its details have no `file`

#### Scenario: A refused override of a continued Crawl names its key
- **WHEN** a stopped Crawl is continued with the override `0` for `crawl.concurrency`
- **THEN** the error has the code `invalid_value`, exit code 2 and `details.key` `"crawl.concurrency"`, and the Crawl's file is unchanged

#### Scenario: A refused flag names its setting
- **WHEN** `linx crawl site.test --concurrency 0` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and `details.key` `"crawl.concurrency"`
