## Why

The product is OpenLinx, but the code, the docs and the specs still use the working name `spider`: the command, the Python package, `spider.toml`, the `.spider/` folder, the robots token. Every name a user types or a site sees must be the product's before the first release, and the open branches need one mechanical way to follow.

## What Changes

- **Names:**
  - The command is `linx`. `openlinx` is a second console script with the same entry point, for a machine where another package's `linx` comes first on PATH.
  - The distribution, the import package and the files are `openlinx`: `openlinx.toml`, the `.openlinx/` data folder, `~/.openlinx`, the environment prefix `OPENLINX_`.
  - The product name in prose is OpenLinx.
- **The robots user-agent token** is `openlinx` by default.
- **What users see:**
  - `--version` prints `OpenLinx <version>`;
  - `commands` names the tool `openlinx`;
  - the usage line names the script that ran, `linx` or `openlinx`, and `crawl.command_argv` starts with it; hints name `linx`.
- **Not renamed:**
  - The Crawl Mode value `spider` and the term Spider mode: they name how a Crawl finds URLs, not the product.
  - The archived changes, which are history.
- **No migration:** no `.spider/` folder or `spider.toml` is read or moved, since nothing was released under the working name.
- **One codemod**, `rename-openlinx.py`, kept outside the repository, makes the bulk of the edit. Each open branch runs it before it merges the rename.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `workspace`: `openlinx.toml`, `.openlinx/`, `linx init`, the data folder's `.gitignore` text.
- `cli-contract`: the command name, `--version`, `linx commands`, the two console scripts.
- `crawl-store`: `crawl.command_argv`, `linx schema`, the data folder paths.
- `crawling`: `linx crawl`, `openlinx.toml`, the robots user-agent token.

## Impact

- Every module moves from `spider` to `openlinx`, and every test, script, doc and plan that names the old package, command or files follows.
- Open branches (`022`, `026`, `030`, `040`, `050`): each runs the codemod on its tree, then merges main.
- `022`'s User-Agent becomes `OpenLinx/<version> (+https://openlinx.dev)`.
