## Context

The working name `spider` is in the import package, `pyproject.toml`, `spider.naming` and every test, doc and spec that names the command or its files. `spider.naming` already holds every name users see, so most of the code reads the name from one place. Several branches are open, each far behind main.

## Goals / Non-Goals

**Goals:** every name a user types, reads or finds on disk is the product's; the open branches follow with one script and small merges.

**Non-Goals:** reading or moving a `.spider/` folder or a `spider.toml`; renaming the Crawl Mode `spider`; editing archived changes; the release and the PyPI upload (`085`).

## Decisions

### D1. Three names
- **In short:** the command is `linx`, the package and everything on disk is `openlinx`, and prose says OpenLinx.
- `openlinx.naming` holds them, and no other module types them (a guard checks it):
  - `COMMAND_NAME = "linx"`: examples, hints, Click's name, the default head of `crawl.command_argv`;
  - `PACKAGE_NAME = "openlinx"`: the distribution, `version()`, `.openlinx`, `openlinx.toml`, the robots token, `commands`' tool name, and the identifiers other changes give on disk (the Skill folder, the plugin, the MCP server);
  - `PRODUCT_NAME = "OpenLinx"`: prose, `--version` and the User-Agent's product token.
- There is no single `APP_NAME`: a name always says which of the three it is.
- **Why the files are `openlinx`:** another package on PyPI also installs a `linx` script, so the long name is the one that stays stable on disk.
- *Alternative:* one name for everything, `linx` or `openlinx`. `linx` collides on disk and on PyPI; `openlinx` is long to type. Rejected.

### D2. The Crawl Mode value stays
- **In short:** `spider` as the Crawl Mode, in `crawl.crawl_mode` and the term Spider mode, is not the product name, and it stays.
- It is stored in every crawl file and listed in the schema with `list` and `sitemap`, which `024` adds.
- *Alternative:* rename the mode with the product. It changes the crawl file's contract, and the mode's name says how a Crawl finds URLs, which the product's name does not. Rejected.

### D3. One codemod, outside the repository
- **In short:** `.git/tools/rename-openlinx.py` makes the whole mechanical edit, and every open branch runs the same script before it merges the rename.
- **What it does:** `git mv src/spider src/openlinx`, then an ordered table of line rewrites over every tracked text file. It masks the kept spans first (D2, Spider mode, `test_spider_mode`, ADR-0006's dated measurement), and keeps each file's bytes and line endings.
- **What it never touches:** `openspec/changes/archive/`, `openspec/specs/` (the archive changes those), and this change's own folder.
- **How it is checked:** it refuses a dirty tree, a second run changes nothing, and `--check` exits 1 when a run would change anything. It prints every `spider` left outside the kept spans.
- **The table is frozen at the codemod commit:** each branch merges that commit after its own run, so the script must reproduce it exactly. A fix to what the table wrote goes in a later commit by hand, which a branch then merges like any other change.
- **Why outside the repository:** it is a one-time migration tool, which branches run on their own tree. Kept in the repository, it would be renamed by its own run.
- **The branches' order:** merge main up to the commit before the codemod, run the script and commit, then merge the codemod commit, then the rest of main. Both sides made the same `git mv` and the same line edits, so the merge pairs the renames.
- *Alternative:* hand edits per area. Branches would conflict on every line both touched. Rejected.

### D4. Usage and the recorded command line name the invoked script
- **In short:** the usage line and `crawl.command_argv[0]` name the script that ran, `linx` or `openlinx`, and `linx` when the tool runs some other way, such as `python -m openlinx`. Hints name `linx`.
- The runner takes the name from the script's file name and gives it to Click as the program name, so the usage line and the recorded command line agree.
- **Why hints stay `linx`:** they are built in five layers (the store, the Workspace, the crawl engine, the services and the runner), and some are stored in the crawl file, in `crawl.warnings`. A per-process name would need a parameter through each of those layers.
- *Alternative:* the invoked name as a parameter of every function that builds a hint. It changes signatures that the open branches call, against D3's small merges, and a stored warning would record whichever script ran. Rejected.
- *Alternative:* rewrite `linx <Command>` at the output edge. It misses the document's `warnings` and `crawl.warnings` unless they are rewritten too. Rejected.

### D5. `--version` names the product
- **In short:** `--version` prints `OpenLinx <version>` whichever script ran, so a `linx` on PATH can be told from another package's.
- *Alternative:* `linx <version>`, the command's name. Another package's `linx` could print the same line. Rejected.

### D6. Deltas generated from the codemod, then edited
- **In short:** `--deltas` writes the delta specs from `openspec/specs` with the codemod's table, the behaviour this change adds is edited into them by hand, and the main specs change only when the change is archived.
- A requirement whose text changes is MODIFIED, and RENAMED too when its name changes. A requirement whose scenario titles change is REMOVED and ADDED again, since OpenSpec refuses a MODIFIED block that renames a scenario; on archive it moves to the end of its spec.
- The hand edits: `--version`, the data folder's `.gitignore` text, the messages and hints that name the product, `crawl.command_argv`, the startup allowlist's module, and the ADDED requirement for the two console scripts.
- *Alternative:* the codemod edits `openspec/specs` directly, with a delta that only describes the rename. The main specs would change before the archive, and validation would not see the change's requirements. Rejected.

## Risks / Trade-offs

- [`022`'s User-Agent names `https://openlinx.dev`, which needs a page that explains the crawler before `022` merges] → Its owner publishes the page; until then the URL is in `022`'s plan only.
- [Another package's `linx` comes first on PATH] → `openlinx` runs the same entry point (D1), and `--version` tells them apart (D5). `080` still has to plan its PATH check to look for `openlinx` too and to warn about a foreign `linx`.
- [A user on the `openlinx` fallback reads hints that say `linx`, which may run the other package (D4)] → `--version` identifies ours (D5), and the warning that `080` still has to plan names `openlinx`.
- [A branch's own new code uses the product name in prose, which the codemod maps to `COMMAND_NAME`] → `test_no_working_name` and the tests that pin hint text catch it, and the branch's review checks each prose use.
- [Tests named after no scenario, which the scenario check does not count] → In `tests/cli/test_init.py`: `test_the_template_names_the_product`, which guards the settings template's first line, which no spec states. In `tests/cli/test_version.py`: `test_version_as_a_real_process_prints_the_same_bytes`, the scenario "Version" in a real process.
- [Scenarios of earlier changes whose tests predate the naming rule, which the scenario check over this change's deltas reports as missing] → The 13 of `cli-contract` and the 2 of `workspace` keep their tests' names; each test still drives its scenario.
- [Crawl files made under the working name keep `["spider", ...]` in `crawl.command_argv`] → It is what was run, and it stays.

## Migration Plan

The codemod commit, then the hand-written commits; the branches follow D3's order.

## Open Questions

None.
