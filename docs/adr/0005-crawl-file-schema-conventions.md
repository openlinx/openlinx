# The crawl file's schema conventions

The crawl file is a public contract ([ADR-0002](0002-sqlite-crawl-store-public-schema.md)), and from v0.1 every change to it costs a migration. So its whole v0.1 shape is decided in one blueprint, before the changes that add tables are built, and every table follows the same rules. Agents read the schema through `linx schema` and `docs/schema.md`, and they learn one convention once rather than one per table.

## Decisions

- **One blueprint for v0.1** (decided 2026-10-10): every table, its column types, nullability, keys, references, CHECKs and indexes are decided before `020-add-crawl-core` is built. The specs of 020, 022, 030, 040 and 060 follow it.
- **Derived values may be stored** (2026-10-10), but only a post-crawl pass writes them. Each one is marked "Derived" in the schema. Examples are the inlink counts of `pages` and the Health Score on `crawl`. A count that only repeats rows another table holds is not stored: `issues.affected_count` is dropped, and a COUNT over an index replaces it.
- **Later columns exist from v0.1** (2026-10-10). A column that a later release fills is in the v0.1 schema as NULL, and its description says from which release it is filled. The `pages` contract is then stable from v0.1.
- **Enumerations are TEXT with a CHECK** (2026-10-10), and so are the 0/1 flags. The file itself refuses a value outside the list. `links` would get integer codes only if a benchmark showed a large gain, and the 2026-10-10 benchmark did not: about 5% of insert time.
- **Indexes are built while the Crawl writes, never after it** (2026-10-11). An agent queries a detached Crawl while it runs, so the indexes behind those queries must exist then. Their write cost is paid during the Crawl.
- **Every Link occurrence is a row** (2026-10-11). "Who links to X" returns every source, with navigation, header and footer Links included, as in Screaming Frog's Inlinks. How the rows are laid out on disk is chosen by measurement, behind the documented `links` columns.
- **STRICT tables.** Every table is declared `STRICT`, so a column's type is enforced and not just an affinity. Reading a crawl file needs SQLite 3.37 or later.

## Naming rules

1. **Tables:** plural snake_case nouns, except the one-row `crawl`. A table of pairs is named after what one row is (`affected_urls`).
2. **Keys:**
   - An entity's own key is `id`, INTEGER.
   - Only public identifiers that a user types are TEXT: the crawl id (`crawl.id`) and the Rule id (`rules.id`).
   - A child table with a natural key uses it, such as `pages.url_id` or `links (source_url_id, ordinal)`.
3. **References:**
   - A reference is named `<table singular>_id` and is declared as a foreign key.
   - When a table refers to the same table twice, a role prefix tells the roles apart: `source_url_id`, `target_url_id`, `redirect_url_id`, `found_on_url_id`.
4. **Time:**
   - A time we record ends in `_at`, as UTC text `YYYY-MM-DDTHH:MM:SS.sssZ`.
   - A header's raw value keeps the header's name and its text (`last_modified`).
5. **Quantities:**
   - The unit is a suffix: `_ms`, `_seconds`, `_bytes`, `_px` or `_pct` (a share from 0 to 100). A count ends in `_count`.
   - A score is neither (`health_score`).
6. **Flags:**
   - INTEGER 0 or 1, refused otherwise.
   - A flag reads as yes or no: `is_*`, `has_*`, `in_*`, a past participle (`parsed`, `body_truncated`), or an HTML token (`rel_nofollow`).
   - A flag is never negated.
7. **Enumerations:**
   - TEXT, with lowercase snake_case values, refused outside the list.
   - Values that a later release adds are listed from v0.1.
   - One enumeration has one value set in every table that holds it, such as `stop_reason`.
8. **URL text:**
   - `url` is the normalised URL. `seeds.url` is the exception: it is the Seed as given.
   - `address` is Screaming Frog's display form, used in `pages` only.
   - A URL that is also a crawled row is referenced by an `_id`. A text copy exists only where it is a Screaming Frog column.
9. **One word, one meaning:**
   - `origin` means scheme://host:port only.
   - A bare `status` is only Screaming Frog's reason phrase in `pages`.
   - "Blocked by robots.txt" is spelled `blocked_by_robots_txt` everywhere.
10. **Errors:** a code column with listed values, plus `<code column>_message` for the text. A code is never a prefix inside free text.
11. **JSON:** only for recorded inputs and for lists that no query filters, sorts or counts by. Anything that a Rule or a documented query filters on is a column.
12. **Descriptions:**
    - Every table, column and index has one.
    - A derived column's description starts with `Derived: `.
    - A column that a later release fills starts with `Filled from v<major>.<minor>. `.
13. **Indexes:**
    - An index is named `<table>_<columns>`.
    - Each one is declared with a description of the query it serves. An index that serves no named query is not added.
    - Indexes are part of the schema description and of `docs/schema.md`.
14. **Screaming Frog names stay.** Every column of `pages` keeps Screaming Frog's name, even where a rule above would choose another. Such columns are renamed only by an explicit decision, as `health_score_pct` became `health_score`.
15. **Layout:**
    - `WITHOUT ROWID` for tables with a natural composite key and narrow rows.
    - `INTEGER PRIMARY KEY` (a rowid alias) for entity tables.

## Consequences

- `linx schema` and `docs/schema.md` describe keys, references, allowed values, derived and later columns, and indexes. A test keeps them equal to the declaration and to a new file.
- CHECKs and STRICT make the file refuse bad values, whatever writes them. A bug in a later change fails at its first write instead of leaving a wrong value for agents to read.
- Every change that adds a table follows these rules from its first slice, and a review checks the rules a test cannot.
- The value lists and the later columns are in the v0.1 file, so v0.2 fills them without a migration. Adding a value or a column that was not foreseen is a schema change: a version bump and a migration.
- Tools built on SQLite older than 3.37 cannot open crawl files.
- An enumeration's CHECK lists its values as equalities joined by OR, never as an `IN (...)` list: SQLite builds an ephemeral index for an IN list of more than two values on every row of an executemany, which made the `urls` insert about 6 times slower (diagnosis of 2026-10-14). The meaning is the same, NULL included.
