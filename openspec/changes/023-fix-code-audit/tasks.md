Seams are those of docs/testing.md. A guard is proven red by a mutation, and the commit body shows its message. Each group ends with its review on the two axes of CONTRIBUTING.md, standards and spec, then one refactor commit with the whole suite green.

## 1. Guards and small fixes

- [x] 1.1 ruff selects `PGH004`, and the guard `test_only_the_streams_and_click_compat_suppress_tid251` keeps the `noqa: TID251` lines in `src/` to those of `openlinx.cli.click_compat` and the runner's raw streams (design D15). Done when: ruff reports a bare `# noqa` on a probe file, and the guard is red with a fourth suppression.
- [x] 1.2 `_declare` refuses a repeated code and a code whose level and exit code disagree (design D15). Done when: a repeated declaration fails at import, naming the code, and so does an error code without an exit code.
- [x] 1.3 Drive "A hidden option is not described" at seam 1, with a hidden option on a fixture-app Command (design D14).
- [x] 1.4 Drive "No environment variable is honoured" at seam 1: `environment` is empty, and docs/workspace.md drops the proxy sentence (design D14).
- [x] 1.5 The docs-link guard covers AGENTS.md, CONTEXT.md, ROADMAP.md and `tests/fixture_site/README.md`, and resolves heading anchors (design D15). Done when: it is red with a broken `#common-changes`.
- [x] 1.6 Every guard asserts with a `<rule>: <fix>` message, the startup guard's fix being "import it inside the function body", and docs/architecture.md's startup allowlist names the pydantic that `linx commands` loads (design D15). Done when: the commit body quotes the messages of two guards made red by mutation, the startup guard's among them.
- [x] 1.7 The `--where` home (design D8): docs/architecture.md's crawl store and package map, the `openlinx.query` docstring, and the sqlalchemy guard's message. Done when: the guard is red with an `import sqlalchemy` in `openlinx.query`, showing the message.
- [x] 1.8 Test support: `run_cli_process` gets `PROCESS_TIMEOUT`, and the bare `pytest.raises(TypeError)` of the command-meta, settings-table and hooks tests match their problem text. Done when: each `match=` is red with a `TypeError` raised for another reason. The timeout has no red proof, since only a hung process shows it, and the commit body says so.
- [x] 1.9 The Hypothesis strategy of `test_the_robots_directives_parser_accepts_any_values` generates its values cheaply enough that the health check passes under the shared lock, with no health check suppressed and no setting loosened. Done when: the commit body gives the per-run times before and after, alone and under the lock.
- [x] 1.10 Review.

## 2. Engine

- [x] 2.1 Guard `test_a_stop_flag_set_off_its_loop_is_refused` at seam 4, with a real loop and a real thread (design D1), and the class docstring's line; the rank test sets the flag on a loop. Done when: it is red on main, where the off-loop set returns and sets the flag.
- [x] 2.2 An extractor whose function is nested or a lambda is refused when it is built, at seam 4; and the guard `test_the_default_page_settings_pickle` (design D2). Done when: the refusal is red first, and the guard is red with a closure-built extractor in `default_hooks()`.
- [x] 2.3 Drive "A failing handler names its error", "A failing extractor names its error" and "A preparation that gave nothing names no error" at seam 3+6 (design D3): `PreparedPage` carries the extractor failures, the warnings' details, their codes' descriptions and docs/crawling.md's warning table gain `error` and `at`, and `page_result` prints them; the guard `test_an_error_raised_in_a_library_points_at_the_extractor_s_line`. Done when: the commit body shows `page_result`'s message for an extractor broken on purpose.
- [x] 2.4 The race of a skip that a raise overtook, in `tests/crawl/test_warning_log.py`, is driven through `crawl_result` and `FakeFetcher`'s page delays (design D16). Done when: the test is red with the double count put back into `Outcomes`; if the race cannot be staged there, docs/testing.md names `Outcomes` an internal seam and the test stays.
- [x] 2.5 Review.

## 3. Store

- [x] 3.1 Guard `test_every_table_is_declared_in_the_schema_module` in a fresh process, over tables and indexes (design D4), and the schema-service fixture's docstring says why its table is temporary. Done when: it is red with a table declared in `openlinx.store.pages`.
- [x] 3.2 Drive "A sync submit under a loop's commit deadline is refused" and "A unit submitted under a loop's commit deadline commits at the deadline" at seam 2, on `FakeClock` (design D5), the deadline's scenario a guard proven by mutation; leaving `loop_deadline()` gives back the writer's own timer and its sync calls; `PassContext.writer` is the `PassWriter` Protocol, proven by a mypy-checked call of `close()` in `tests/test_handler_types.py`; docs/crawl-store.md "When it commits" states both regimes.
- [x] 3.3 Drive "A unit that returns a cursor is refused" and "A unit that commits ends the writer" at seam 2 (design D6), the earlier units' Futures resolving.
- [x] 3.4 The guards `_at` → `timestamp` and `<x>_message` → `<x>` with values over `linx schema` (design D7), and CONTRIBUTING's schema section names what tests check. Done when: each is red with one bad column.
- [x] 3.5 Review.

## 4. The Crawl's input (design D9, D10)

- [x] 4.1 Drive "A refused value given with the settings names its key" at seam 2, through `plan_crawl` with no app, and "A refused given value is reported before a refused file value", and `Settings.table` naming a table that is not registered. `default_tables()` in `openlinx.services.settings`; `build_app`, `plan_crawl` and `init_workspace` use it, the test helpers build no app, and docs/testing.md names it for seam-2 calls.
- [x] 4.2 Drive "A refused override of a continued Crawl names its key" at seam 2, through the mapper that `load_settings` uses.
- [x] 4.3 Drive "A refused flag names its setting" at seam 1: the runner's `invalid_value` takes `details.key` from the option's setting.
- [x] 4.4 `CrawlRequest` gets `subdomains` and `secret_flags` in place of `secret_names`, and `plan_crawl` resolves the alias and its conflict and builds the secret names, at seam 2 with the conflict's existing scenario kept at seam 1. The CLI adapter only maps flags.
- [x] 4.5 Drive "Bounds of an option" at seam 1: `min` and `max` in `linx commands` and docs/cli.md.
- [x] 4.6 The import rule: `openlinx.services`, `.workspace`, `.store`, `.crawl`, `.extract` and `.output` import no `typer` and no `openlinx.cli`. Done when: it is red with a `typer` import in a service.
- [x] 4.7 Guard `test_mirrored_options_match_their_fields` over every Command (design D10), replacing the hidden rule in the recorded-config test, which compares with `CrawlSettings()`. Done when: it is red with Click's `max` changed and with a `[crawl]` field that has no option.
- [x] 4.8 Review.

## 5. Link reading and the Link type table

Starts only after the pull request of `030`'s group 11 (link counts and Folder Depth) is merged into main, and after a merge of main into this branch. If it is late, groups 4 and 6 run first, 6.1 apart.

- [ ] 5.1 `locate_links` returns by ordinal and refuses a subset, at seam 4 (design D11), on a Page whose `<nav>` and `<main>` link the same URL; `openlinx.extract.page_links` reads the mapping. Done when: the subset case is red on main, where it returns the `<nav>` element.
- [ ] 5.2 Guard `test_every_name_used_across_a_package_is_listed`, with the lists of `openlinx.crawl.pages` and `openlinx.crawl.fetch` completed, and docs/architecture.md's pointer to `locate_links` (design D13). Done when: it is red on main's lists and green after them.
- [ ] 5.3 `LINK_TYPES` in `openlinx.store.records`, with `LinkElement` and `LinkAttribute` beside `LinkType`; the follow rule, `RESOURCE_LINK_TYPES` and discovery's selectors derive from it; `DiscoveredLink.element` and `attribute` are typed, and `link_handler`'s cast goes; `discovered_link` moves to `openlinx.crawl.references`, under the factory guard (design D12). Done when: the Link type and link extractor tables pass unchanged, and the factory guard is red with a `DiscoveredLink(...)` built in a pages module.
- [ ] 5.4 `030`'s element guard compares pairs with `LINK_TYPES`, and the guard `test_link_type_table_matches_the_docs` (design D12). Done when: they are red with a table pair that discovery does not read, with a Literal value that has no pair, and with a Requested cell changed.
- [ ] 5.5 Review.

## 6. Docs and recipes

- [ ] 6.1 CONTRIBUTING's hooks recipe in numbered steps over the real built-ins: the `page_links` extractor, the `links` handler and its writer in `openlinx.store.links`, the inlink pass, `default_hooks()`, the seams to test at, and what checks each step; drop "020's planned reworks". Gated like group 5, since the inlink pass comes with `030`'s group 11. Done when: each step names a file of `src/` and a test that exists, and the docs-link guard passes.
- [ ] 6.2 Two column recipes, a column the crawl writes and a column a handler writes, each with its files in order and `replay_now`; the setting recipe says a `[crawl]` setting always gets an option; the code recipe says how to choose `kept=`. Done when: each named file and test exists, and each step names what checks it or is marked *review*.
- [ ] 6.3 docs/testing.md lists the formulas of design D16 at seam 4, names the implementation pins of the hooks and writer tests, and says that `tests/test_handler_types.py` is checked by mypy. Done when: each named test exists.
- [ ] 6.4 Review: the two axes on the whole change, then refactor with the whole suite green.
- [ ] 6.5 Archive the change: the deltas into `openspec/specs`, `openspec validate --all --strict`. Done when: validation passes and ROADMAP.md marks the change done.
