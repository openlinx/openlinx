"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawl-store/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI, through `run_cli`
- seam 2: the store API, with a real crawl store in `temp_workspace`, writing through `CrawlWriter`
- seam 6: the store contract, `tests/contract/test_schema.py`: `docs/schema.md` against `spider schema --limit 1000`, and a new file through `PRAGMA`

"Done when" says what must be true, not which helper to write. Names appear only where another change depends on them (design, Interface points).

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract. The scenarios that `015` already tests keep their tests and names. A guard over a rule that only later tables can exercise ("Reference columns are declared", "Index names start with their table", "Derived and later columns may hold NULL") passes vacuously in this change. Its assertion that it saw at least one matching column or index switches on in the `020` task that adds the first foreign key or index (design, Risks).

**The whole change is in the thin slice:** `020` starts after it (ROADMAP, Build order). ADR-0005 is committed with the change's planning documents, and the code follows it from the first task.

## 1. The file refuses bad values (seam 2, seam 6)

- [ ] 1.1 Drive "An unknown enumeration value is refused".

  Done when: one declaration helper in `spider.store.schema` adds a CHECK, named `<table>_<column>_values`, for every column with `info["values"]`. It allows NULL for a nullable column. No table writes a CHECK by hand (design D2).
- [ ] 1.2 Drive "A flag outside 0 and 1 is refused". Done when: the same helper adds `<table>_<column>_flag` for every `Flag` column.
- [ ] 1.3 Drive "Every table is strict", at seam 6.

  Done when: the helper declares every public table with `sqlite_strict=True`, and a real number is declared with `sqlalchemy.REAL`, never `Float` or `Double` (design D3).
- [ ] 1.4 Drive "A value of another type is refused".
- [ ] 1.5 **Guard:** `015`'s convention scenarios over the stricter tables: "Names are snake_case", "Descriptions are present", "Booleans are integers", "Enumeration values are snake_case" and "Timestamp text".
- [ ] 1.6 **Guard:** `015`'s "Crawl metadata" scenarios, unchanged by the revised rule on counts: "Metadata of a new Crawl", "Seeds keep their order", "Version stamp", "Environment stamp", "Completion time" and "A stopped Crawl has no completion time". Also `015`'s "Unmeasured values are NULL" scenarios: "A running Crawl has no completion time" and "No settings file".
- [ ] 1.7 Docs: in `docs/schema.md`, replace "Conventions" with ADR-0005's rules as the spec states them (D1): STRICT, CHECKs, keys and references, `_at`, the units with `_seconds` and `_count`, errors, the two description prefixes, indexes. State that reading a crawl file needs SQLite 3.37 or later. In "How to add a table", add the declaration helper, `REAL`, and an index's `info["description"]`. Link ADR-0005.
- [ ] 1.8 Review: run the code-review skill on group 1's commits against "Public schema conventions" and ADR-0005, then refactor with the whole suite green.

## 2. The schema description: references, indexes and markers (seam 1, seam 6)

- [ ] 2.1 Drive "Self-description of schema" at seam 1. Done when: `spider schema` lists `indexes` as an available and default field.
- [ ] 2.2 Drive "A table without secondary indexes lists none" at seam 1.

  Done when:
  - each item's `indexes` lists the table's secondary indexes in name order, without primary-key indexes
  - each index gives `name`, `description` (from the index's `info["description"]`), `columns`, `unique` and `where` (design D4)
- [ ] 2.3 **Guard:** "Reference columns are declared", at seam 1.

  Done when: `references` is read from the column's declared foreign key, instead of always `null`. `020`'s `found_on_url_id` is the first column to exercise it.
- [ ] 2.4 **Guard:** "Index names start with their table", at seam 1.
- [ ] 2.5 **Guard:** "Derived and later columns may hold NULL", at seam 1.
- [ ] 2.6 Drive "A new file matches the declaration", at seam 6.

  Done when: the file check also reads `PRAGMA table_list` (STRICT, and `WITHOUT ROWID` where it is declared), `PRAGMA index_list` and `PRAGMA index_xinfo` (the index columns and uniqueness), and `sqlite_master.sql` (a partial index's condition).
- [ ] 2.7 Drive "Documentation and declaration agree", at seam 6.

  Done when:
  - `docs/schema.md` has an "Indexes" table under each table section that has secondary indexes, with Name, Columns, Unique, Where and Description, and its "How to read a table section" explains it
  - the contract test's parser reads that table and compares it with `spider schema --limit 1000`
  - the parser lives in `spider.services.schema_doc.parse_tables(text)`, which the test imports, so that `080` can read its generated reference back with it
- [ ] 2.8 **Guard:** `015`'s other scenarios of "Listing the schema with spider schema", with `indexes` in the items: "One table", "First tables", "Columns of seeds", "Column formats", "The next page", "Unknown table", "Internal tables are hidden", "No Workspace needed", "Global flags of schema" and "Default limit of schema".
- [ ] 2.9 Docs: in `docs/crawl-store.md`, say that `spider schema` describes references and indexes, that a derived column is written only by a post-crawl pass, and that a later column is NULL until its release.
- [ ] 2.10 Review: run the code-review skill on group 2's commits against "Listing the schema with spider schema" and "The documented schema, the declared schema and the file agree", then refactor with the whole suite green.

## 3. Change check

- [ ] 3.1 Verify that every `#### Scenario:` in `specs/crawl-store/spec.md` has exactly one test named after it, with a small script over the test ids.
- [ ] 3.2 Docs: the "Crawl store" section of `docs/architecture.md` names ADR-0005, and says that the declaration helper is the one way to declare a public table.
- [ ] 3.3 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 3.4 Review: run the code-review skill on the whole change against `specs/crawl-store/spec.md` and ADR-0005, then refactor with the whole suite green.
