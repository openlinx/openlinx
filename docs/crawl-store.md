# The crawl store

How `spider` stores each Crawl. The spec is [openspec/changes/015-add-crawl-store/specs/crawl-store/spec.md](../openspec/changes/015-add-crawl-store/specs/crawl-store/spec.md), and the tables are documented in [schema.md](schema.md). Terms follow [CONTEXT.md](../CONTEXT.md).

## Crawl files

Each Crawl is one SQLite file in the `crawls/` folder of the Workspace's data folder ([workspace.md](workspace.md)):

```
~/work/shop/.spider/crawls/20260927-140312-k3f9.sqlite    a Crawl of the local Workspace ~/work/shop
~/.spider/crawls/20260927-140312-k3f9.sqlite              a Crawl of the global Workspace
```

- The file name is the crawl id followed by `.sqlite`.
- The file holds everything the Crawl recorded, with the public schema of [schema.md](schema.md), so it can be copied, archived or attached to a bug report on its own.
- Every new file is built from the schema the tool declares, and a test checks that its tables and columns are exactly the documented ones.

## The data folder

Storing a Crawl needs no `spider init` first. Creating a Crawl creates whatever is missing of the data folder, as `spider init` would:

| Created | When |
|---|---|
| `.spider/` | the data folder is missing |
| `.spider/.gitignore` | it is missing; it makes git ignore the crawl data |
| `.spider/crawls/` | it is missing |

- **No settings file.** Creating a Crawl never writes `spider.toml`. Only `spider init` does.
- **The global Workspace.** When no local Workspace is found, the Crawl goes to `~/.spider/crawls/`, and `~/.spider/` is created when it is missing.
- **An unwritable data folder** fails with `workspace_not_writable` (exit code 7) before anything is crawled. `details.path` names the path that failed, for example `~/.spider` when it is a file instead of a folder.
