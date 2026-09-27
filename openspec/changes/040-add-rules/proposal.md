## Why

`030-add-page-data` stores what each Page contains, but not what is wrong with it. Agents need deterministic findings with fixed guidance to prioritise and explain problems without guessing, because the tool never calls an LLM ([ADR-0004](../../../docs/adr/0004-tool-never-calls-an-llm.md)). The Report and `summary` also need a Health Score that means the same thing in every Crawl. This change adds the Rules, the Issues they produce and the Health Score, using Screaming Frog's model of Issue Type × Priority.

## What Changes

- **The Rule model.** Each Rule has:
  - a stable kebab-case id and a category
  - an Issue Type (`issue`, `warning` or `opportunity`) and a Priority (`high`, `medium` or `low`)
  - what it applies to: `internal_urls`, `internal_pages` or `resources`
  - when it is evaluated: `during_crawl` or `post_crawl`
  - thresholds with defaults
  - three guidance texts: `description`, `why_it_matters` and `how_to_fix`
- **The v0.1 catalogue of 42 Rules** in 10 categories: `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images`.
  - The maintainer approved keeping all 42 Rules on 2026-09-27.
  - `http-url` is a Warning with High Priority, so it never lowers the Health Score.
  - Categories are snake_case enumeration values; Rule ids stay kebab-case.
- **Configuration in `spider.toml`.** `[rules.<id>]` tables override thresholds (for example `max_chars = 70`) and disable Rules (`enabled = false`). An unknown Rule id, an unknown key or an invalid value is a `settings_invalid` error of `010-add-workspace-and-cli-contract` (exit code 3), checked when the settings load and reported with its dotted key.
- **Evaluation timing.**
  - URL Rules run through `020-add-crawl-core`'s per-response hook, and Page Rules run with each Page's data, in the writer unit that records the URL.
  - Rules that compare Pages or need other URLs' results run in the post-crawl passes, after `030`'s link counts. These are the duplicates, canonical targets, Redirect Chains and loops, and image Resources.
  - The Rule configuration is fixed when a Crawl starts and recorded in the Crawl.
- **New crawl-store tables,** each with column descriptions shown by `spider schema` and documented in `docs/schema.md`:
  - `rules`: the Rules as configured for this Crawl, including their guidance, so a crawl file stays self-contained
  - `issues`: one row per Rule that fired, with `affected_count`
  - `affected_urls`: one row per Rule and URL, with a JSON `detail` of the measured values
- **New crawl metadata fields** on the `crawl` row of `015-add-crawl-store`: `health_score_pct`, `health_internal_pages`, `health_affected_pages` and `health_calculated_at`.
- **The Health Score.** `floor(100 × (Internal Pages − affected Internal Pages) ÷ Internal Pages)` is calculated at the end of the post-crawl passes. A Page counts as affected when it is an Affected URL of any Rule whose Issue Type is `issue`. `050` and `070` call the same function for Segments.
- **New Command `spider rules [list | show <id>]`.**
  - It prints JSON with each Rule's id, category, Issue Type, Priority, what it applies to, evaluation timing, enabled state, effective thresholds (value, default, unit) and guidance texts.
  - It follows `010`'s output contract (paging envelope, `--fields`, `--limit`, `--cursor`, `--format`).
  - An unknown id fails with `rule_not_found` (exit code 4).
  - No MCP tool is added here; `090-add-mcp-server` mirrors `rules`.

## Capabilities

### New Capabilities
- `rules`: the Rule model, the v0.1 catalogue, threshold overrides and disabling, evaluation during the Crawl and in the post-crawl passes, stored Issues and Affected URLs, the Health Score and the `spider rules` Command.

### Modified Capabilities
_None._ No specs exist yet. This change builds on requirements of `010`, `015`, `020`, `022` and `030` and does not modify them.

## Non-goals

- Rules that need the whole link graph, such as orphan Pages, hreflang return links and sitemap coverage: v0.2.
- `rules apply`, which recomputes the Issues of a stored Crawl after thresholds change: v0.2. In v0.1 a Crawl keeps the Issues computed with the configuration it recorded.
- Structured-data validation Rules: v0.3.
- Near-Duplicate Rules: v0.3.
- The full Rule set, and Rules for directives found outside `<head>`: v1.0.
- Overriding a Rule's Issue Type or Priority in `spider.toml`: not planned for v0.1. See design.md, Open Questions.
- Third-party Rule plugins and translated guidance: backlog.
- `issues`, `summary` and per-Segment Issue counts, which belong to `050-add-query-and-segments`. The Report, which belongs to `070-add-html-report`.

## Impact

- **Depends on:**
  - `010-add-workspace-and-cli-contract` for `spider.toml` validation (`settings_invalid`), the output contract, error codes and exit codes
  - `015-add-crawl-store` for the table conventions, `docs/schema.md`, the `crawl` row and the transactional writer
  - `020-add-crawl-core` for the `urls` table (`is_internal`, `status_code`, `fetch_state`, `fetch_error`, `blocked_by_robots`, `parsed`), the per-response hook, the post-crawl passes hook, the injectable clock and resuming through the Crawl Service
  - `022-add-fetch-policy` for `redirect_url_id`, `redirect_loop`, `size_bytes` and the Resource checks
  - `030-add-page-data` for `pages`, `links`, the stored Indexability and the link counts
- **Consumers:**
  - `050`: `issues`, `summary`, per-Segment Health Score
  - `070`: the Health Score, Issues, how-to-fix text, and the mapping from categories to Report Sections
  - `080`: the Skill's Rules reference, generated from `spider rules list`
  - `090`: the `rules` MCP tool
- **Code:** `src/spider/rules/` (registry, Rule modules, thresholds, evaluation, Health Score), `src/spider/cli/rules.py`, new tables in `src/spider/store/`, `docs/schema.md`, `docs/rules.md`, and hooks in the crawl pipeline.
- **Dependencies:** none new.
