Seams are those of docs/testing.md. A guard is proven red by a mutation, and the commit body shows its message. Each group ends with its review on the two axes of CONTRIBUTING.md, standards and spec, then one refactor commit with the whole suite green.

## 1. Guards and small fixes

- [x] 1.1 ruff selects `PGH004`, and the guard `test_only_the_streams_and_click_compat_suppress_tid251` keeps the `noqa: TID251` lines in `src/` to those of `openlinx.cli.click_compat` and the runner's raw streams (design D15). Done when: ruff reports a bare `# noqa` on a probe file, and the guard is red with a fourth suppression.
- [x] 1.2 `_declare` refuses a repeated code and a code whose level and exit code disagree (design D15). Done when: a repeated declaration fails at import, naming the code, and so does an error code without an exit code.
- [x] 1.3 Drive "A hidden option is not described" at seam 1, with a hidden option on a fixture-app Command (design D14).
- [x] 1.4 Drive "No environment variable is honoured" at seam 1: `environment` is empty, and docs/workspace.md drops the proxy sentence. Integration note: `022` supersedes this completed correction with its honoured proxy family; preserve its tests and contract (design D14).
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
- [x] 4.6 The import rule: no module outside `openlinx.cli` and `openlinx.__main__` imports `typer` or `openlinx.cli`, and ruff's `TID252` bans relative imports, which would hide the name. Done when: it is red with a `typer` import in a service and in `openlinx.query`.
- [x] 4.7 Guard `test_mirrored_options_match_their_fields` over every Command (design D10), replacing the hidden rule in the recorded-config test, which compares with `CrawlSettings()`. Done when: it is red with Click's `max` changed and with a `[crawl]` field that has no option.
- [x] 4.8 Review.

## 5. Link reading and the Link type table

Starts only after the pull request of `030`'s group 11 (link counts and Folder Depth) is merged into main, and after a merge of main into this branch. If it is late, groups 4 and 6 run first, 6.1 apart.

- [x] 5.1 `locate_links(tree, links, *, expected_total)` refuses every proper subset relative to the original `len(page.links)`, checks count, ordinals 1 to N and headers-first before filtering, and returns HTML locations by ordinal in frozen `LocatedLink` records (design D11); `openlinx.extract.page_links` passes the original count and reads the mapping, preserving DOM reference matching. At seam 4 in `tests/crawl/test_links.py`, use real Links from preparation: dropped-tail, second-only nav/main Links to the same URL, omitted header Links and a header-only Page's omitted Links must be red before the fix; an empty Page and complete header 1 / nav 2 / main 3 give the expected mapping. Done when: these cases pass, existing DOM matching tests remain green, and the subset cases were red because the old implementation accepted them.
- [x] 5.2 Guard `test_every_name_used_across_a_package_is_listed`, over the imports in `src`, with the lists of `openlinx.crawl.pages`, `openlinx.crawl.fetch` and `openlinx.crawl.engine` completed, and docs/architecture.md's pointer to `locate_links` (design D13). Done when: it is red on main's lists and green after them.
- [x] 5.3 `LINK_TYPES` in `openlinx.store.records`, with `LinkElement` and `LinkAttribute` beside `LinkType`; the follow rule, `RESOURCE_LINK_TYPES` and discovery's selectors derive from it; `DiscoveredLink.element` and `attribute` are typed, and `link_handler`'s cast goes; `discovered_link` moves to `openlinx.crawl.references`, under the factory guard, and the tests that built `DiscoveredLink` go through it; `openlinx.crawl.following`'s docstring drops its promise about shortest paths (design D12). Done when: the Link type and link extractor tables pass unchanged, and the factory guard is red with a `DiscoveredLink(...)` built in a pages module.
- [x] 5.4 `030`'s element guard compares pairs with `LINK_TYPES`, and the guard `test_link_type_table_matches_the_docs` (design D12). Done when: they are red with a table pair that discovery does not read, with a Literal value that has no pair, and with a Requested cell changed.
- [x] 5.5 Review.

## 6. Docs and recipes

Before these slices, integrate main at `4957b1879f3a13b22ef0e322f2fc15bfc0b12e50`
into the isolated branch based on `7ffa39e59da3e9b4b808b06ff838ca54a1a1c3b7`.
`030` group 11 is already present; do not repeat it. Resolve the four previewed
conflicts deliberately: keep both the complete-Link contract and the expanded
`UrlResponse` in docs/architecture.md, both packages' real interface names in
`crawl/fetch/__init__.py`, `LINK_TYPES`-driven following alongside `022`'s redirect
helpers in `crawl/following.py`, and verified current status in docs/development-state.md.
`references` imports `following.skip_reason`; importing `references.resolve_reference`
at the top of `following` would create a cycle. Extract the pure URL resolution
functions and their helpers/constants into `crawl/reference_urls.py` (design D12).
Both modules import the needed names from that leaf at module level; `references`
explicitly re-exports its existing resolver names and `C0_OR_SPACE`. Preserve the
Link factory and record in `references`, and `redirect_target` in `following`.
Prove cold imports in both orders and preserve the reference/redirect behaviour
at seam 4; update the crawl package's module list and check the import guards.
Review the automatically merged records, schema, Scope/URL tests and import guards
as well: keep `022`'s redirect provenance, attempts, response sizes and headers,
and `023`'s canonical Link types, source metadata, factories and complete-Link checks.
Preserve `022`'s proxy contract, tests and self-description; the workspace delta
adds only the refused-value requirement, and must not remove the proxy exception.
Focused tests, a serialized full gate and source review precede the recipe slices.

- [x] 6.1 CONTRIBUTING's hooks recipe in numbered steps over the real built-ins: the `page_links` extractor, the `links` handler and its writer in `openlinx.store.links`, the inlink pass, `default_hooks()`, the seams to test at, and what checks each step; drop "020's planned reworks". Use the integrated `services/hooks.py::count_inlinks` pass and `store/links.py` units, not an assumed pass module. Done when: each step names a file of `src/` and a test that exists; extractor preparation, handler mapping, writer replay and pass execution have their own checks, any additional review-only obligations are explicit, and the docs-link guard passes.
- [x] 6.2 Two column recipes, a column the crawl writes and a column a handler writes, each with its files in order and `replay_now`; the setting recipe says a `[crawl]` setting always gets an option; the code recipe says how to choose `kept=`. Done when: each named file and test exists, and each step names what checks it or is marked *review*.
- [x] 6.3 docs/testing.md lists the formulas of design D16 at seam 4, names the implementation pins of the hooks and writer tests, and says that `tests/test_handler_types.py` is checked by mypy. Done when: each named test exists.
- [ ] 6.4 Review: the two axes on the whole change, including integration and recipes, then any justified refactor with the whole suite green. Preserve incoming `022` contracts and all completed audit guards; review both the change against current main and the integration resolutions.
- [ ] 6.5 Archive the change: the deltas into `openspec/specs`, `openspec validate --all --strict`. Done when: all preceding tasks are accepted, validation passes, the merged specs retain the proxy exception and every `022` contract, and ROADMAP.md marks the change done. Coordinate `022` task 10.1 with its owner: its planned modification of "Environment variables change nothing" must target the retained "No environment variables" requirement instead, so neither archive removes or duplicates the environment requirement.
