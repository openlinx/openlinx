# Rules

How a Crawl's data becomes Issues: the Rules, what their Issue Type and Priority mean, and how to read `spider rules`. The spec is [openspec/changes/040-add-rules/specs/rules/spec.md](../openspec/changes/040-add-rules/specs/rules/spec.md), and terms follow [CONTEXT.md](../CONTEXT.md).

## The Rule model

A Rule is a deterministic check with fixed guidance. Every Rule has:
- `id`: kebab-case, such as `title-too-long`. It is never renamed or reused, so a script or a `spider.toml` that names it keeps working.
- `category`: one of `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images`, in this order.
- `issue_type` and `priority`: see below.
- `applies_to`: the population the Rule checks. `internal_urls` are the Internal URLs that were requested, or that robots.txt disallows; `internal_pages` are the analysed Pages ([page-data.md](page-data.md#analysed-and-non-analysed-pages)); `resources` are the Resources that Pages reference, in v0.2 the images.
- `thresholds`: the named limits of the Rule, each a non-negative integer with a default and a unit (`characters`, `pixels`, `words`, `kilobytes` or `hops`). A Rule without limits has none.
- `description`, `why_it_matters` and `how_to_fix`: fixed English guidance, the same in every Crawl, so an agent can explain an Issue without judgement calls.

v0.1 ships 15 Rules. The other 27 of the catalogue come in v0.2.

## Issue Type and Priority

The Issue Type says how certain the problem is:
- `issue`: a definite defect, such as a page that answers 404. Issue-type Issues alone lower the Health Score.
- `warning`: something to check, which can be intended, such as a redirect, a noindex Page or a URL that robots.txt blocks.
- `opportunity`: something that could be better, such as a title that search engines cut short.

The Priority says how urgently to fix it: `high`, `medium` or `low`.

`issue` is kept for definite defects because it decides the Health Score: anything that can be intended is a `warning`. `http-url`, a Page served over plain HTTP, is a Warning with High Priority: it comes first among the Warnings, while the Health Score still reflects the site's other defects.

## Names

Categories are snake_case, such as `meta_descriptions`, because they are stored values of an enumeration, and every stored enumeration value is snake_case. Rule ids are kebab-case, such as `meta-description-missing`, because people type them as command arguments and as `spider.toml` table names, where `-` is allowed.

## Reading `spider rules`

`spider rules list` lists the Rules in catalogue order: by category, in the order above, then in the order of the spec's tables. It is a list Command ([cli.md](cli.md#lists-paging-fields-and-cursors)), so it takes `--limit` (50 by default), `--cursor`, `--fields` and `--format`, and `--workspace` for a Workspace other than the nearest one. `spider rules` with no arguments runs `spider rules list`; options go after `list`. Each item has `id`, `category`, `issue_type`, `priority`, `applies_to`, `enabled`, `thresholds`, `description`, `why_it_matters` and `how_to_fix`:

```
spider rules list --limit 1
{"total":…,"items":[{"id":"internal-4xx","category":"response_codes","issue_type":"issue","priority":"high","applies_to":"internal_urls","enabled":true,"thresholds":{},"description":"An Internal URL responded with a client error, a status code from 400 to 499.","why_it_matters":"…","how_to_fix":"…"}],"next_cursor":"…"}
```

`spider rules show <id>` prints one Rule as a document with the same fields. `enabled` is false for a Rule that the Workspace turns off, and `thresholds` maps each limit's name to its `value` in the Workspace, its `default` and its `unit`:

```
spider rules show title-too-long
{"id":"title-too-long","category":"titles","issue_type":"opportunity","priority":"medium","applies_to":"internal_pages","enabled":true,"thresholds":{"max_chars":{"value":60,"default":60,"unit":"characters"}},…}
```

An id that no Rule has fails with `rule_not_found` (exit code 4), whose hint points to `spider rules list`.

## Settings: `[rules.<id>]`

A table named by a Rule's id in the Workspace's `spider.toml` changes that Rule in the Workspace, as `spider rules` shows it.

Raise a limit, here the title length, from 60 to 70 characters:

```toml
[rules.title-too-long]
max_chars = 70
```

Turn a Rule off, which `spider rules` shows as `enabled` false:

```toml
[rules.h1-missing]
enabled = false
```

A table may hold `enabled`, a boolean, and the Rule's thresholds by name, each an integer from 0 to 2^63-1, SQLite's largest INTEGER; `spider rules show <id>` lists a Rule's thresholds. Anything else stops every Command that reads the settings with `settings_invalid` (exit code 3), before a Crawl requests any URL. `details.errors[].key` is the dotted key, and the hint names the closest Rule id or key when there is one:

```
spider rules list
{"level":"error","code":"settings_invalid","message":"The settings file …/spider.toml is invalid.","hint":"Did you mean rules.title-too-long?","details":{"file":"…/spider.toml","errors":[{"key":"rules.title-to-long","message":"Extra inputs are not permitted"}]}}
```
