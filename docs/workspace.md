# The Workspace

Where `spider` keeps its Crawls and settings, and how every Command finds them. The spec is `openspec/changes/010-add-workspace-and-cli-contract/specs/workspace/spec.md` until the change is archived, then `openspec/specs/workspace/spec.md`. Terms follow [CONTEXT.md](../CONTEXT.md).

## Layout

A Workspace has a root, a data folder and a settings file.

| Workspace | Data folder | Settings file |
|---|---|---|
| local, rooted at a folder | `<root>/.spider/` | `<root>/spider.toml` |
| global | `~/.spider/` | `~/.spider/spider.toml` |

- Crawls live in the data folder's `crawls/` folder.
- The data folder is git-ignored by its own `.gitignore`. `spider.toml` sits next to it, so a team can commit the settings without the crawl data.
- The global Workspace keeps its settings inside `~/.spider/`, so the home folder itself gets no `spider.toml`.

## Finding the Workspace

A Command that uses a Workspace takes the first of these that applies:

1. **`--workspace <dir>`.** A relative path is taken from the current folder. When the folder does not exist, the Command fails with `workspace_not_found` (exit code 4). `spider init` is the exception: it creates the folder.
2. **The nearest marked folder.** The search starts at the current folder and goes up one parent at a time. A folder is a Workspace when it contains `.spider/` or `spider.toml`. Either one alone is enough, so a fresh clone of a repository with a committed `spider.toml` is a Workspace before anyone runs `spider init` in it.
3. **The global Workspace.**

**The search stops at the home folder.** Reaching it selects the global Workspace, so a Workspace above the home folder is never found by searching; name it with `--workspace` instead. When the current folder is not inside the home folder, for example on another drive, the search goes up to the top of that drive.

**The home folder is never a local Workspace.** Running from the home folder, or passing it with `--workspace`, selects the global Workspace. That includes any spelling of it, such as `~/work/..` or a symlink, because paths are resolved before they are compared. A file `~/spider.toml` is never read.

```
~/work/shop/spider.toml        the Workspace of every folder below ~/work/shop
~/work/shop/blog/              → root ~/work/shop
~/work/notes/                  → no marker up to ~ → the global Workspace, ~/.spider/
```

On Windows, `--workspace` accepts `/` as well as `\`, and home folders with non-ASCII names work like any other.

## No environment variables

No environment variable selects the Workspace, sets a setting or changes a Command's output. The only inputs are flags, `spider.toml`, and the operating system's own home folder and current folder. There is no `SPIDER_WORKSPACE`: MCP clients pass `spider mcp --workspace <dir>` instead.

There are two exceptions:
- **Proxy variables.** `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY`, in any letter case, are honoured for fetching, because they are the operating system's network configuration. They are the only variables that `spider commands` lists under `environment`.
- **Detection signals.** Variables that host agents set, such as Codex's `CODEX_SANDBOX_NETWORK_DISABLED`, may shape the wording of diagnostics and hints. They never change a result, an exit code, the Workspace or a setting.

## Creating a Workspace: `spider init`

`spider init` makes a folder a local Workspace: the current folder, or the folder given with `--workspace`. It creates the folder and any missing parents.

```
spider init
spider init --workspace ~/work/shop
```

It creates only what is missing, and never changes a file that exists. A `spider.toml` already in the folder, for example one committed to the repository, is kept byte for byte. Running it twice is safe: the second run creates nothing.

| Created | Content |
|---|---|
| `.spider/` | the data folder |
| `.spider/.gitignore` | `# Created by spider: crawl data is not committed.` and `*`, so git ignores the data folder's contents |
| `.spider/crawls/` | where Crawls are stored |
| `spider.toml` | the settings file, which sets no value |

For the home folder, `spider init` sets up the global Workspace instead, and its settings file is `~/.spider/spider.toml`.

The result on stdout:

```json
{"workspace":"/home/ana/work/shop","data_dir":"/home/ana/work/shop/.spider","settings_file":"/home/ana/work/shop/spider.toml","global":false,"created":["/home/ana/work/shop/.spider","/home/ana/work/shop/.spider/.gitignore","/home/ana/work/shop/.spider/crawls","/home/ana/work/shop/spider.toml"]}
```

| Key | Value |
|---|---|
| `workspace`, `data_dir`, `settings_file` | absolute paths |
| `global` | `true` only for the home folder |
| `created` | the paths this run created, in the order of the table above; `[]` when nothing was missing |

Diagnostics on stderr:
- **`workspace_nested`** (warning, exit code 0): a folder above the new Workspace, below the home folder, is already a Workspace. `details.parent` is its root. Commands run below the new Workspace now use it.
- **`workspace_not_writable`** (error, exit code 7): the folder or its data folder cannot be created or written, for example because a path segment is a file. The message names the folder.
