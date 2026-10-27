## MODIFIED Requirements

### Requirement: Commented settings template
**In short:** `spider init` writes a `spider.toml` that sets nothing and shows every setting commented out; a table of named tables, such as `[rules.<id>]`, shows only its commented header.

The `spider.toml` written by `spider init` SHALL be valid TOML that sets no value. It SHALL start with a comment that names the precedence (flag, then `spider.toml`, then default). For every setting the tool knows, except those of a table of named tables, it SHALL contain:
- the setting's table header, uncommented
- a comment describing the setting
- the commented-out line `# <key> = <default>`, or `# <key> =` for a setting that is unset by default

A keyed table SHALL appear as a comment describing it and the commented-out header `# [<table>.<name>]`, followed by the commented-out lines of an entry's settings.

A table of named tables SHALL appear as a comment describing it and the commented-out header `# [<table>.<name>]`, with no settings lines, since each of its named tables has settings of its own, such as the thresholds of a Rule in `[rules.<id>]` (`040-add-rules`). A table opts into this kind explicitly; a table of tables that does not is refused.

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

#### Scenario: A table of named tables in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains a comment that names `spider rules list`, followed by the line `# [rules.<name>]`, and no line `# max_chars = 60`

#### Scenario: Template loads as defaults
- **WHEN** the settings of `H/work/shop` are resolved right after `spider init` created its `spider.toml`
- **THEN** they are equal to the settings resolved for the Workspace `H/work/empty`, which has `.spider/` but no `spider.toml`
