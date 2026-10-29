Seams are those of docs/testing.md: seam 1 is the CLI through `run_cli`, "seam 1, subprocess" a real process. The codemod is `.git/tools/rename-openlinx.py` (design D3), outside the repository.

## 1. Plan

- [x] 1.1 Proposal, design, tasks, and the delta specs that `rename-openlinx.py --deltas` writes from `openspec/specs`, with the ADDED requirement for the two console scripts. Done when: `openspec validate 021-rename-to-openlinx --strict` passes.

## 2. The codemod

- [ ] 2.1 Run the codemod on a clean tree, then `ruff check --select I --fix` and `ruff format`, `uv lock`, and `uv sync`. In the same commit, add the guard `test_no_working_name`: no `spider` outside the kept spans of design D2 and D3, the archive, `openspec/specs` and this change's folder.
  Done when: check.py passes; a second run of the codemod changes nothing and `--check` exits 0; the codemod reports no `spider` left; and the guard is red with one `spider` planted in `src`, in `docs` and in a test.

## 3. The three names (design D1, D4, D5)

- [ ] 3.1 Drive "Version" at seam 1: `--version` prints `OpenLinx <version>`, from `PRODUCT_NAME` in `openlinx.naming`. Done when: the scenario's delta says so.
- [ ] 3.2 Prose names the product: "a bug in OpenLinx", "Upgrade OpenLinx to read it", and `# Created by OpenLinx: ...` in the data folder's `.gitignore`, each through `PRODUCT_NAME`, each with its delta and a test red first.
- [ ] 3.3 Drive hints and usage that name the invoked command (design D4): `linx` or `openlinx` from the script's name, `linx` otherwise; `crawl.command_argv[0]` records it. Done when: a seam-1 subprocess test runs both scripts and finds each name in its own usage text and `resume` hint, and the deltas say so.

## 4. The second console script

- [ ] 4.1 Drive "Both console scripts run the same entry point": `openlinx = "openlinx.cli.app:main"` beside `linx`. The test reads the distribution's `console_scripts` entry points.
- [ ] 4.2 The CI wheel smoke test runs `linx --version` and `openlinx --version` and compares their output.

## 5. Docs

- [ ] 5.1 The prose the codemod leaves to people: README's opening, `CONTRIBUTING.md`'s names paragraph with `PRODUCT_NAME`, `AGENTS.md`, and `docs/` wherever a sentence now reads wrong. Done when: a read of each changed paragraph finds the right one of the three names.

## 6. Guards

- [ ] 6.1 `tests/test_naming.py` refuses the literals `openlinx.toml`, `.openlinx`, `"linx"`, `"openlinx"` and `"OpenLinx"` in `src/` outside `openlinx.naming`, red by a planted literal.

## 7. Review and archive

- [ ] 7.1 Review: the code-review skill on the change, then refactor with the whole suite green.
- [ ] 7.2 Archive the change; `openspec/specs` takes the deltas, and `test_no_working_name` drops `openspec/specs` from its exceptions.
