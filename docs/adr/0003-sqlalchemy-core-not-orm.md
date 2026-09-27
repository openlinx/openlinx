# SQLAlchemy Core, not the ORM, for crawl data

Crawl data is written and filtered through SQLAlchemy 2 Core table definitions, not ORM objects. A 500k-page crawl produces tens of millions of Link rows, and creating an ORM object per row would make the write path an order of magnitude slower.

Core still gives us one schema definition that drives:
- batched inserts from a single writer
- safe `--where` → SQL translation that allows only known columns
- Alembic migrations
- the generated SQL reference used by `spider schema` and the Skill

## Considered Options

- **Full ORM or SQLModel everywhere**: the cleanest code, but too slow for Pages and Links.
- **Peewee**: lighter, but its query builder is weaker and it has no Alembic.
- **Raw sqlite3**: the fastest, but it leaves hand-written SQL strings everywhere.

## Consequences

- ORM-mapped classes are allowed only for small tables, such as crawl metadata and control rows.
