## Purpose

Lets people and agents split a Crawl's Pages into named Segments, written in `spider.toml` with the `--where` language and applied at query time. Every query Command, the Health Score and the Report can then be read for one part of a site without crawling again.

## ADDED Requirements

### Requirement: Segment definitions in spider.toml

Segments SHALL be defined in the Workspace's `spider.toml`, found and loaded as `010-add-workspace-and-cli-contract` defines, as a `[segments]` table.
- Each key is a Segment name, and each value is a `--where` expression over the `pages` columns.
- The order of the keys in the file SHALL be the order in which Segments are evaluated.
- A Segment name SHALL be 1 to 64 characters from `A`–`Z`, `a`–`z`, `0`–`9`, `_` and `-`. Names are case-sensitive.

#### Scenario: Segments in file order
- **WHEN** `spider.toml` contains `[segments]` with `shop = "address ~ '/shop/'"` on the first line and `blog = "address ~ '/blog/'"` on the second
- **AND** `spider summary` runs
- **THEN** the `name` values of `segments` are `shop` and `blog`, in that order

#### Scenario: Membership follows the expressions
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"` and `shop = "address ~ '/shop/'"`, and the Crawl has the Pages `https://example.com/blog/a`, `https://example.com/blog/b`, `https://example.com/shop/c` and `https://example.com/about`
- **AND** `spider pages --fields address,segment` runs
- **THEN** the items are `{"address": "https://example.com/about", "segment": null}`, `{"address": "https://example.com/blog/a", "segment": "blog"}`, `{"address": "https://example.com/blog/b", "segment": "blog"}` and `{"address": "https://example.com/shop/c", "segment": "shop"}`, in that order

### Requirement: Segment definitions are checked when settings load

Every Segment definition SHALL be checked eagerly, as part of the settings check that `010-add-workspace-and-cli-contract` runs whenever `spider.toml` is loaded. A name that breaks the naming rule, or an expression that is not a valid `--where` expression over the `pages` columns, SHALL make every Command that loads `spider.toml` fail with `settings_invalid` (exit code 3) before it does anything else. There SHALL be one `details.errors` entry per invalid Segment. Its `key` is `segments.<name>`, and its `message` holds the problem, for example the `--where` error and its position.

#### Scenario: Unknown column in a Segment expression
- **WHEN** `spider.toml` defines `broken = "adress ~ '/x/'"`
- **AND** `spider summary` runs
- **THEN** the exit code is 3, the error has the code `settings_invalid`, and `details.errors[0].key` is `"segments.broken"`

#### Scenario: The problem is named
- **WHEN** `spider.toml` defines `broken = "adress ~ '/x/'"`
- **AND** `spider summary` runs
- **THEN** `details.errors[0].message` contains `adress`

#### Scenario: Invalid Segment name
- **WHEN** `spider.toml` defines `"my segment" = "status_code = 200"`
- **AND** `spider pages` runs
- **THEN** the exit code is 3, and `details.errors[0].message` contains `my segment`

#### Scenario: Commands that do not use Segments are stopped too
- **WHEN** `spider.toml` defines `broken = "adress ~ '/x/'"`
- **AND** `spider pages --where "status_code = 200"` runs
- **THEN** the exit code is 3, and stdout is empty

### Requirement: First match wins

Each Page SHALL belong to the first Segment, in evaluation order, whose expression is true for it. A Page for which no Segment expression is true SHALL belong to no Segment.

#### Scenario: Overlapping Segments
- **WHEN** `spider.toml` defines `news = "address ~ '/blog/news/'"` and then `blog = "address ~ '/blog/'"`
- **AND** `spider page https://example.com/blog/news/x` runs
- **THEN** `segment` is `news`

#### Scenario: Reordering changes membership
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"` and then `news = "address ~ '/blog/news/'"`
- **AND** `spider page https://example.com/blog/news/x` runs
- **THEN** `segment` is `blog`

#### Scenario: A Page in no Segment
- **WHEN** `spider.toml` defines only `blog = "address ~ '/blog/'"`
- **AND** `spider page https://example.com/about` runs
- **THEN** `segment` is `null`

### Requirement: Segments are applied at query time

Segment membership SHALL be computed from the current `spider.toml` every time a Command runs, and SHALL NOT be stored in the Crawl. Adding, changing, removing or reordering Segments SHALL change the results of the next Command without crawling again. It applies equally to every Crawl in the Workspace, older Crawls included.

#### Scenario: Editing a definition changes the next result
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"`, and the Crawl has the Pages `https://example.com/blog/a`, `https://example.com/shop/c` and `https://example.com/about`
- **AND** `spider pages --segment blog` runs, then the definition is changed to `blog = "address ~ '/'"`, and `spider pages --segment blog` runs again
- **THEN** `total` is `1` in the first output and `3` in the second

#### Scenario: Segment changes do not touch the store
- **WHEN** a Segment definition is changed and `spider pages --segment blog` runs again
- **THEN** a SQL dump of the crawl store is identical to one taken before the change

#### Scenario: Older Crawls use the current definitions
- **WHEN** the Workspace holds an older Crawl A with the Page `https://example.com/blog/a`, and `blog = "address ~ '/blog/'"` is added to `spider.toml` after Crawl A reached the state `completed`
- **AND** `spider pages --crawl <id of Crawl A> --segment blog` runs
- **THEN** `total` is `1`

### Requirement: The --segment flag

`summary`, `pages`, `issues`, `issues <rule-id>` and `export` SHALL accept `--segment <name>`. It restricts the Command to the Pages that belong to that Segment by first-match membership, and it combines with `--where` so that both must hold. An unknown name SHALL be rejected with the error code `unknown_segment` (exit code 2), whose `details.accepted` lists the defined Segment names in evaluation order. When no Segments are defined, the hint SHALL explain how to add a `[segments]` table to `spider.toml`. `070-add-html-report` uses the same resolution for `report --segment` and `report brief --segment`.

#### Scenario: Pages of one Segment
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"` and `shop = "address ~ '/shop/'"`, and the Crawl has the Pages `https://example.com/blog/a`, `https://example.com/blog/b`, `https://example.com/shop/c` and `https://example.com/about`
- **AND** `spider pages --segment blog` runs
- **THEN** `total` is `2`

#### Scenario: A Page won by an earlier Segment is not in a later one
- **WHEN** `spider.toml` defines `news = "address ~ '/blog/news/'"` and then `blog = "address ~ '/blog/'"`, and the Crawl has the Pages `https://example.com/blog/news/x` and `https://example.com/blog/y`
- **AND** `spider pages --segment blog --fields address` runs
- **THEN** `items` is `[{"address": "https://example.com/blog/y"}]`

#### Scenario: --segment combines with --where
- **WHEN** the Segment `blog` holds the Pages `https://example.com/blog/a` (status code 200) and `https://example.com/blog/b` (404), and `https://example.com/about` (404) is in no Segment
- **AND** `spider pages --segment blog --where "status_code = 404" --fields address` runs
- **THEN** `items` is `[{"address": "https://example.com/blog/b"}]`

#### Scenario: Unknown Segment name
- **WHEN** `spider.toml` defines `blog` and then `shop`
- **AND** `spider pages --segment blgo` runs
- **THEN** the exit code is 2, and the error has the code `unknown_segment` and `details.accepted` `["blog", "shop"]`

#### Scenario: --segment without any Segments defined
- **WHEN** `spider.toml` has no `[segments]` table
- **AND** `spider summary --segment blog` runs
- **THEN** the error has the code `unknown_segment` and a hint that contains `[segments]` and `spider.toml`

### Requirement: The segment field

`pages` and `export pages` SHALL offer a `segment` field, the name of the Page's Segment or `null`, through `--fields` and `--fields all`. `page <url>` SHALL always include `segment`. `--sort` SHALL accept `segment`. `segment` SHALL NOT be usable in `--where`: there it SHALL be rejected with the error code `unknown_column`, and the hint SHALL mention `--segment`.

#### Scenario: Sorting by Segment
- **WHEN** the Pages `https://example.com/about` (no Segment), `https://example.com/shop/c` (Segment `shop`) and `https://example.com/blog/a` (Segment `blog`) are listed with `spider pages --sort segment --fields address`
- **THEN** the addresses are `https://example.com/blog/a`, `https://example.com/shop/c` and `https://example.com/about`, in that order

#### Scenario: segment in --where
- **WHEN** `spider pages --where "segment = 'blog'"` runs
- **THEN** the exit code is 2, and the error has the code `unknown_column` and a hint that contains `--segment`

### Requirement: Issues within a Segment

Under `--segment`, an Issue's `affected_count` SHALL count only the Affected URLs that are Pages of that Segment, and Issues left with none SHALL be omitted. Affected URLs that are not Pages, such as Resources, SHALL belong to no Segment.

#### Scenario: Counts within a Segment
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/blog/a`, `https://example.com/blog/b` and `https://example.com/shop/c`, and the Segment `blog` holds the first two
- **AND** `spider issues --segment blog` runs
- **THEN** the item for `title-missing` has `"affected_count": 2`

#### Scenario: Issues without Affected URLs in the Segment are omitted
- **WHEN** the Issue `h1-missing` has only the Affected URL `https://example.com/shop/c`, which is in the Segment `shop`
- **AND** `spider issues --segment blog` runs
- **THEN** no item has the `rule_id` `h1-missing`

#### Scenario: Resources belong to no Segment
- **WHEN** the only Affected URL of the Issue `image-broken` is the image Resource `https://example.com/blog/img/a.png`, and `blog = "address ~ '/blog/'"` is defined
- **AND** `spider issues --segment blog` runs
- **THEN** no item has the `rule_id` `image-broken`

#### Scenario: Affected URLs of one Issue within a Segment
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/blog/a`, `https://example.com/blog/b` and `https://example.com/shop/c`, and the Segment `blog` holds the first two
- **AND** `spider issues title-missing --segment blog` runs
- **THEN** `total` is `2`

### Requirement: Health Score of a Segment

The Health Score of a Segment SHALL apply the Health Score function of `040-add-rules` to the Segment's Internal Pages only, in the same `{score, internal_pages, affected_pages}` form as the summary's `health_score`. It SHALL be `{"score": null, "internal_pages": 0, "affected_pages": 0}` when the Segment has no Internal Pages.

#### Scenario: Health Score of one Segment
- **WHEN** the Segment `blog` holds 4 Internal Pages, 1 of which is an Affected URL of an *Issue*-type Issue
- **AND** `spider summary --segment blog` runs
- **THEN** `health_score` is `{"score": 75, "internal_pages": 4, "affected_pages": 1}`

#### Scenario: Empty Segment
- **WHEN** `spider.toml` defines `empty = "address ~ '/nothing-here/'"`, and no Page matches it
- **AND** `spider summary` runs
- **THEN** the `health_score` of the `empty` entry in `segments` is `{"score": null, "internal_pages": 0, "affected_pages": 0}`

### Requirement: Per-Segment breakdown in summary

When at least one Segment is defined and `--segment` is not given, the summary's `segments` member SHALL list one entry per defined Segment, in evaluation order, including Segments with no Pages.
- Each entry SHALL have exactly the members `name`, `where`, `pages`, `status_classes`, `indexability`, `health_score` and `issues`.
- They are computed over that Segment's Pages and have the same shapes as the summary members of those names. In an entry, `status_classes.external` is `null`.
- The summary's `unsegmented` member SHALL have the same members, with `name` and `where` set to `null`, for the Pages in no Segment.

When no Segment is defined, `segments` SHALL be `[]` and `unsegmented` SHALL be `null`.

#### Scenario: Entries add up to all Pages
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"` and `shop = "address ~ '/shop/'"`, and the Crawl has the Pages `https://example.com/blog/a`, `https://example.com/blog/b`, `https://example.com/shop/c` and `https://example.com/about`
- **AND** `spider summary` runs
- **THEN** the `pages` values of `segments` are `2` and `1`, and `unsegmented.pages` is `1`

#### Scenario: Entry members
- **WHEN** `spider.toml` defines `blog = "address ~ '/blog/'"` and `spider summary` runs
- **THEN** the keys of the `blog` entry are exactly `name`, `where`, `pages`, `status_classes`, `indexability`, `health_score` and `issues`, and its `where` is `address ~ '/blog/'`

#### Scenario: Issues per Segment
- **WHEN** the Issue `title-missing` has the Affected URLs `https://example.com/blog/a`, `https://example.com/blog/b` and `https://example.com/shop/c`, and `blog` and `shop` are defined as above
- **AND** `spider summary` runs
- **THEN** the `affected_count` of `title-missing` in `issues.top` is `2` in the `blog` entry and `1` in the `shop` entry

#### Scenario: Summary without any Segments defined
- **WHEN** `spider.toml` has no `[segments]` table and `spider summary` runs
- **THEN** the output contains `"segments": []` and `"unsegmented": null`

### Requirement: Summary of one Segment

`spider summary --segment <name>` SHALL compute every summary member over the Pages of that Segment only, and SHALL set `segment` to the name.
- `segments` SHALL be `[]` and `unsegmented` SHALL be `null`.
- A Segment contains only Pages, so `totals.urls`, `totals.internal_urls` and `totals.pages` SHALL all equal the number of the Segment's Pages.
- `totals.external_urls`, `totals.resources` and `status_classes.external` SHALL be `null`.

Without `--segment`, `segment` SHALL be `null`.

#### Scenario: Totals of one Segment
- **WHEN** the Segment `blog` holds 2 Pages, and the Crawl also recorded 3 External URLs and 4 Resources
- **AND** `spider summary --segment blog` runs
- **THEN** `totals` is `{"urls": 2, "internal_urls": 2, "external_urls": null, "pages": 2, "resources": null}`

#### Scenario: Segment members of a one-Segment summary
- **WHEN** `spider.toml` defines `blog` and `shop`, and `spider summary --segment blog` runs
- **THEN** the output contains `"segment": "blog"`, `"segments": []` and `"unsegmented": null`

#### Scenario: Whole-Crawl summary
- **WHEN** `spider summary` runs without `--segment`
- **THEN** the output contains `"segment": null`
