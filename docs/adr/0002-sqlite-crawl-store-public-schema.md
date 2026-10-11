# One SQLite file per Crawl, with a public schema

Every Crawl is stored as its own SQLite file in the Workspace. Its schema is a documented, versioned public contract, and agents may query it directly with read-only SQL (`spider sql`). Agents are good at SQL and ask questions that no fixed set of commands anticipates, so we give up the freedom to reshape tables at will in exchange for that flexibility.

## Consequences

- Once v0.1 ships, every schema change needs an Alembic migration and a schema version bump. Older crawl files are migrated when opened.
- Before v0.1 ships there are no migrations: a change edits the declared tables directly, and the schema version stays 1, where the contract starts.
- `spider sql` opens crawl files read-only and rejects anything that is not a read.
- WAL mode lets agents query while a crawl is writing. On network drives, where WAL does not work, the store falls back to rollback-journal mode and warns that queries must wait for the crawl.
- A crawl file is self-contained, so it can be copied, archived or attached to a bug report.
