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

## Crawl ids

A crawl id is the Crawl's UTC start time and 4 random characters:

```
20260927-140312-k3f9
YYYYMMDD-HHMMSS-xxxx
```

- **Sortable:** ids sort by start time, to the second, so `ls` lists Crawls in the order they started.
- **The random characters** come from `0123456789abcdefghjkmnpqrstvwxyz`. It leaves out `i`, `l`, `o` and `u`, so an id read aloud or copied by hand is not mistaken for another.
- **Never a taken id:** an id is taken when its crawl file exists. A new Crawl whose drawn id is taken draws new random characters until the id is free.
- **Two processes cannot get the same id.** The crawl file is created exclusively, so when two processes draw the same id in the same second, only one of them creates the file and the other draws again.

## The data folder

Storing a Crawl needs no `spider init` first. Creating a Crawl creates whatever is missing of the data folder, as `spider init` would:

| Created | When |
|---|---|
| `.spider/` | the data folder is missing |
| `.spider/.gitignore` | it is missing; it makes git ignore the crawl data |
| `.spider/crawls/` | it is missing |

- **No settings file.** Creating a Crawl never writes `spider.toml`. Only `spider init` does.
- **The global Workspace.** When no local Workspace is found, the Crawl goes to `~/.spider/crawls/`, and `~/.spider/` is created when it is missing.
- **An unwritable data folder** fails with `workspace_not_writable` (exit code 7) before anything is crawled. `details.path` names the path that failed, for example `~/.spider` when it is a file instead of a folder, or the new crawl file when `crawls/` does not allow creating files. A permissions problem never shows up as a traceback.

## What a Crawl records about itself

Every crawl file has a one-row table `crawl` with the Crawl's metadata and a table `seeds` with its Seeds. [schema.md](schema.md) documents every column; in short:

| Recorded | Columns |
|---|---|
| what was crawled, and how | `crawl_mode` (`spider`, `list` or `sitemap`), `section_crawl`, and the Seeds in `seeds`, in the order given (`position` 1, 2, …) |
| where it stands | `state`, `started_at`, `completed_at` |
| how it was started | `command_argv`, `cwd`, `settings_file`, `config` |
| what made the file | `tool_version`, `schema_version` (also SQLite's `user_version`), `journal_mode`, `python_version`, `platform` |

- **Counts are not recorded.** No column holds the number of URLs, Pages or Issues: they are counted from the tables that hold them, so they can never disagree.
- **`started_at`** is the same instant as the time in the crawl id, read once when the Crawl is created.
- **`settings_file`** is the `spider.toml` the settings were read from, or NULL when there was none. `config` holds the settings the Crawl ran with, with every table and key, so the file says how it was made even when `spider.toml` changes later.
- **The environment stamp** (`python_version` and `platform`) helps when a crawl file is attached to a bug report.

## Crawl States

`state` holds one of the Crawl States, as [CONTEXT.md](../CONTEXT.md) defines them:

| State | Meaning |
|---|---|
| `running` | a process is crawling, or was when it last wrote the file |
| `stopped` | paused before its end, resumable |
| `completed` | it ran to the end |
| `failed` | it could not continue, resumable |
| `interrupted` | its process died without recording an end, resumable |

Resuming arrives with `060-add-crawl-control` (v0.2).

- A new Crawl starts as `running`.
- `completed_at` is set when the state becomes `completed`, and is NULL in every other state. A `stopped` or `failed` Crawl has no completion time.
- A `running` state does not prove that a process is still crawling: a process that was killed leaves it behind. Telling the two apart is `060-add-crawl-control`'s job, which records such a Crawl as `interrupted`.

## Writing a Crawl

Creating a Crawl writes its file, its `crawl` row and its Seeds in one transaction. Everything written after that goes through the Crawl's writer, in **units of work**.

- **A unit** is a function that gets a database connection and may insert, update and read rows. It returns a value to its caller, for example the next URL to fetch.
- **One at a time, in order.** The writer runs units on its own thread, one at a time, in the order they were submitted. Units can come from several threads, or from an event loop without blocking it.
- **One open transaction.** Every unit sees what the units before it wrote, committed or not, so a unit can read a row and update it in one step.
- **Atomic units.** A unit that fails leaves no change: its writes are rolled back, its error reaches its caller, and the units before and after it are unaffected. That holds for Ctrl+C inside a unit too.
- **When it commits:**

  | Trigger | |
  |---|---|
  | 500 units since the last commit | the batch |
  | 1 second after the first unit since the last commit | the timer, checked after each unit and every 50 ms while idle |
  | `flush()` | at once, before `flush()` returns |
  | `close()` | everything still open |

- **What a crash loses.** A process that is killed loses at most the units since the last commit: up to 500 units, or about a second of work. Committed units survive, and the file stays sound.
- **The write check.** Opening the writer first runs a write that it rolls back. A crawl file that cannot be written, for example one with the read-only attribute, fails at once with `crawl_not_writable` (exit code 7) and `details.file`, before anything is crawled, and the file is left unchanged.
- **One writer per Crawl.** In v0.1 only the process that creates a Crawl writes it, because a Crawl cannot be resumed or detached yet. `060-add-crawl-control` adds a claim on the file when a second process can write.
- **After `close()`,** the writer accepts no more units: a unit submitted then fails at once. Closing twice is harmless.

## Not measured is NULL

A value that was not measured, or that does not apply, is stored as NULL, never as `0` or an empty string. `0` is a measured zero, and an empty string is a value that is present but empty. So `completed_at` is NULL while a Crawl runs, and `settings_file` is NULL when there was no settings file. Queries should test `IS NULL`, not `= 0` or `= ''`.
