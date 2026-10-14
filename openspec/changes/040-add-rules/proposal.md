## Why

`030-add-page-data` stores what each Page contains, but not what is wrong with it. Agents need deterministic findings with fixed guidance to prioritise and explain problems without guessing, because the tool never calls an LLM ([ADR-0004](../../../docs/adr/0004-tool-never-calls-an-llm.md)). The Report and `summary` also need a Health Score that means the same thing in every Crawl. This change adds the Rules, the Issues they produce and the Health Score, using Screaming Frog's model of Issue Type × Priority.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships 15 Rules of the catalogue, listed under "The v0.1 Rules" in ROADMAP.md. **Deferred to v0.2:** the other 27 Rules. In v0.1 `title-too-long` checks characters only, because pixel widths are v0.2.
>
> **SQL per Rule (2026-10-05):** every v0.1 Rule ships a reproducing SQL query over the public schema, stored in `rules.reproduce_sql` (2026-10-11). `rules show <id>` prints the query.
>
> **Rules are only SQL (user decision, 2026-10-11):** every Rule is evaluated only by its query. A running Crawl writes no Issue; the Issues reader computes them live from the queries while a Crawl has no final pass, and the post-crawl pass materialises them into `affected_urls` when the Crawl ends.
>
> **Schema blueprint (2026-10-11):** the tables follow [ADR-0005](../../../docs/adr/0005-crawl-file-schema-conventions.md) and `018-add-schema-conventions`. `rules` is keyed by the Rule id, `issues` is a view that counts each Rule's Affected URLs, so no count is stored, `affected_urls` is keyed by `(rule_id, url_id)` with an index on `url_id`, and the `health_*` fields are derived, with `health_score` in place of `health_score_pct`.

- **The Rule model.** Each Rule has:
  - a stable kebab-case id and a category
  - an Issue Type (`issue`, `warning` or `opportunity`) and a Priority (`high`, `medium` or `low`)
  - what it applies to: `internal_urls`, `internal_pages` or `resources`
  - its reproducing SQL query, which is how it is evaluated
  - thresholds with defaults
  - three guidance texts: `description`, `why_it_matters` and `how_to_fix`
- **The v0.1 catalogue of 42 Rules** in 10 categories: `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images`.
  - The maintainer approved keeping all 42 Rules on 2026-09-27.
  - `http-url` is a Warning with High Priority, so it never lowers the Health Score.
  - Categories are snake_case enumeration values; Rule ids stay kebab-case.
- **Configuration in `spider.toml`.** `[rules.<id>]` tables override thresholds (for example `max_chars = 70`) and disable Rules (`enabled = false`). An unknown Rule id, an unknown key or an invalid value is a `settings_invalid` error of `010-add-workspace-and-cli-contract` (exit code 3), checked when the settings load and reported with its dotted key.
- **Evaluation.**
  - Every Rule is evaluated by its query; no Rule runs while a URL is recorded.
  - While a Crawl has no final pass (it is `running`, `failed` or `interrupted`), the Issues reader runs the queries live, read-only, and returns the shape of the stored Issues.
  - When a Crawl ends as `completed` or `stopped`, the post-crawl pass, after `030`'s link counts, writes each Rule's rows into `affected_urls` and then the Health Score. It runs again when a resumed Crawl ends.
  - The Rule configuration is fixed when a Crawl starts and recorded in the Crawl.
- **New crawl-store tables and a view,** each with column descriptions shown by `spider schema` and documented in `docs/schema.md`:
  - `rules`: the Rules as configured for this Crawl, including their guidance and reproducing queries, so a crawl file stays self-contained
  - `affected_urls`: one row per Rule and URL, with a JSON `detail` of the measured values
  - `issues`: a view with one row per Rule that fired and its `affected_count`, counted from `affected_urls`
- **New derived fields** on the `crawl` row of `015-add-crawl-store`, written only by the post-crawl pass: `health_score`, `health_internal_page_count`, `health_affected_page_count` and `health_calculated_at`.
- **The Health Score.** `floor(100 × (Internal Pages − affected Internal Pages) ÷ Internal Pages)` is calculated at the end of the post-crawl passes. A Page counts as affected when it is an Affected URL of any Rule whose Issue Type is `issue`. `050` and `070` call the same function for Segments.
- **New Command `spider rules [list | show <id>]`.**
  - It prints JSON with each Rule's id, category, Issue Type, Priority, what it applies to, enabled state, effective thresholds (value, default, unit), guidance texts and reproducing query.
  - It follows `010`'s output contract (paging envelope, `--fields`, `--limit`, `--cursor`, `--format`).
  - An unknown id fails with `rule_not_found` (exit code 4).
  - No MCP tool is added here; `090-add-mcp-server` mirrors `rules`.

## Capabilities

### New Capabilities
- `rules`: the Rule model, the v0.1 catalogue, threshold overrides and disabling, Rules as SQL queries, live Issues during a Crawl and their materialisation by the post-crawl pass, stored Issues and Affected URLs, the Health Score and the `spider rules` Command.

### Modified Capabilities
- `workspace`: the commented settings template describes a table of named tables, a third kind of settings table that a table opts into, which `[rules.<id>]` is (design D9). This change builds on other requirements of `010`, `015`, `020`, `022` and `030` without modifying them.

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
  - `015-add-crawl-store` for `docs/schema.md`, the `crawl` row, `NewCrawl` and the writer
  - `017-speed-up-crawl-writer` for the contract of a unit that may run again, and `replay_now(writer)`
  - `018-add-schema-conventions` for the schema conventions (ADR-0005), `public_table()` and the contract test
  - `020-add-crawl-core` for the `urls` table (`is_internal`, `status_code`, `fetch_state`, `fetch_error`, `blocked_by_robots_txt`, `parsed`), the post-crawl passes hook, `default_hooks()` in `spider.services.hooks`, the injectable clock and resuming through the Crawl Service
  - `022-add-fetch-policy` for `redirect_url_id`, `in_redirect_loop`, `size_bytes` and the Resource checks
  - `030-add-page-data` for `pages`, `links`, the stored Indexability and the link counts
- **Consumers:**
  - `050`: `issues`, `summary`, `page <url>` and the per-Segment Health Score, all reading Issues through this change's Issues reader
  - `070`: the Health Score, Issues, how-to-fix text, and the mapping from categories to Report Sections
  - `080`: the Skill's Rules reference, generated from `spider rules list`, and the cost of live Issues during a Crawl against materialised ones
  - `090`: the `rules` MCP tool
- **Code:** `src/spider/rules/` (registry, Rule modules with their queries, thresholds, Health Score), `src/spider/cli/rules.py`, `spider.store.schema` (the tables and the view), `spider.store.issues` (the Issues reader and the post-crawl pass), Command groups in `spider.cli`, `docs/schema.md`, `docs/rules.md`, and the pass's entry in `020`'s `default_hooks()`.
- **Dependencies:** none new.
