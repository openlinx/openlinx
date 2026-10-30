## Context

The hooks seam, the writer and the settings loader work, but several of their rules hold only by convention: a test passes while the rule is broken, and the break shows in production or in another change's branch. Three seams are missing or hidden: services validate settings only through the CLI, the Link reading that `030` needs is not in any package interface, and Link type knowledge is in five modules.

## Goals / Non-Goals

**Goals:**
- every rule of a seam that a contributor can break fails a test or the build, with a message that says the fix;
- a service called without the CLI validates its input as the CLI does;
- one Link type table;
- the recipes and docs describe what is built.

**Non-Goals:**
- the seams that `022`, `026`, `040`, `050`, `060` and `090` add (run watchers, the Fetcher's settings, the network pause's interface, a read interface for the store, the list contract in a service): each change designs its own;
- refactors with no failure behind them (`run_crawl`'s length, the names `unit_of` and `TaskFailure`, a neutral module for the enumerations);
- a schema snapshot per `schema_version`, which starts at the v0.1 tag.

## Decisions

### D1. The stop flag is set only on its loop
- **In short:** `StopSignal.set` raises `RuntimeError` when it is called from a thread with no running loop or from another loop, and the message names `loop.call_soon_threadsafe(stop.set, reason)`.
- The flag binds to the running loop at its first `set` or `wait`, because the Crawl Service builds it before its Runner starts the loop. A test that sets it runs on a loop, as every caller in the product does.
- **Why:** an `asyncio.Event` set from a thread wakes no waiter until the loop wakes for another reason. On `FakeClock` a test wakes by chance; an idle production loop, in a pause or with every slot taken, never wakes. `060`'s control check will run beside the loop, so the mistake is the natural one.
- *Alternative:* `set` hops to the loop by itself with `call_soon_threadsafe`. It hides which thread sets the flag, and the callbacks (the stopping event, the grace) would then run later than their caller assumes. Rejected.

### D2. An extractor is module-level, checked when it is built
- **In short:** `Extractor` refuses a function whose `__qualname__` holds `<locals>` or whose name is `<lambda>`, with "the function of the extractor X is not module-level: a parse worker process imports it by name; pass values through config".
- A guard pickles the `PageSettings` built from `default_hooks()` and checks that it unpickles equal, which is what `026`'s pool does with it. It also catches a config field that does not pickle.
- *Alternative:* `pickle.dumps` of every extractor at build time. It costs a pickle per Crawl and gives a pickle error instead of the rule. Rejected; the guard covers the built-ins and the qualname check covers the rest.

### D3. A hook failure names its error and where it was raised
- **In short:** the first counted `handler_failed` and `parse_failed` warnings carry `details.error`, the error's text cut to 300 characters, and `details.at`, the file and line in the hook where it was raised.
- **Which frame:** the deepest frame of the traceback whose file is the one that defines the hook's function (its `co_filename`), so an error raised in a library the hook calls points at the hook's own line. A `functools.partial` is unwrapped to its function first, since a partial has no code of its own. The file is written relative to the folder that holds its top-level package, with `/` on every OS, so the warning is the same on every machine; a file outside that folder is named by its module's dotted name. With no such frame, as when an extractor returns something other than its declared output and preparation raises, `at` is absent rather than pointing at preparation.
- A preparation that gave nothing (`body_too_large`, `worker_crashed`, `parse_timeout`) raised nothing in a hook, so its warning has neither key.
- Reading the error never fails the URL: an error whose text cannot be read is named by its type.
- `PreparedPage` carries each extractor failure as a small frozen struct (name, error type, text, place), so it crosses `026`'s process boundary. `parse_error_message` stays `name: Type`: it is a public column of every Page, and the text of one error belongs to the warning, which keeps only the first.
- Test helpers that fail on an extractor error (`page_result`) print the same details.
- *Alternative:* a traceback in the details. It is long, holds absolute paths, and differs by OS. Rejected.

### D4. Every table is declared in `openlinx.store.schema`
- **In short:** a guard in a fresh process compares the tables, indexes and views on `metadata` after `import openlinx.store.schema` with those after importing every `openlinx` module, and names any extra one with "declare it in openlinx.store.schema".
- **Why:** `linx schema` and the docs test read only that module, while `create_all` builds whatever was imported. A table declared beside its units would be in the crawl file and missing from the contract, and the contract test would pass or fail by test order.
- *Alternative:* `linx schema` imports every store module. The schema would then depend on import side effects, and the first change to declare a view elsewhere (`040`) would still pass. Rejected.

### D5. A pass gets the writer's async calls only
- **In short:** `PassContext.writer` is a Protocol with `run_async`, `submit_async` and `flush_async`, and under `loop_deadline()` the writer's sync `submit` and `run` raise `RuntimeError("inside a Crawl use submit_async / run_async")`.
- **Why:** under a loop's commit deadline the writer's thread does not commit on its own timer; only the async calls wake the loop's deadline. A sync `submit` therefore waits for 500 units, a flush or the close, which under `FakeClock` hangs the test and in a Crawl delays the pass's units to the end. A pass has no use for `close`.
- `docs/crawl-store.md` "When it commits" states both regimes.
- *Alternative:* the sync `submit` wakes the loop's deadline through `call_soon_threadsafe`. It keeps a call that blocks the loop when the window is full. Rejected.

### D6. The writer refuses a unit it could not replay
- **In short:** at a unit's first run the writer refuses a result that compares by identity, and a unit that commits ends the writer; both errors name the unit's `__qualname__` and the fix ("return values, such as .all() rows or a record"; "never commit").
- **Identity equality:** `type(result).__eq__ is object.__eq__`. For a tuple, list or frozenset, the same check runs over the set of its element types, and for a dict over the set of its key types and its value types, so a tuple of 500 records costs one check per type. An `enum.Enum` member passes: it is a singleton, so identity is its value. A `CursorResult`, a connection-bound object or a plain class is refused; `Row`, records, numbers and strings pass. A refused result leaves no change, as a failing unit does.
- **A commit:** a SQLAlchemy `commit` event listener on the writer's connection, armed while a unit runs, sees a commit wherever the unit makes it. `in_transaction()` after the unit would miss a unit that commits and then executes again, since the connection begins a new transaction by itself. The commit has already written the unit's changes before it and the batch before them, so the writer cannot undo it: it ends, as a failed replay ends it, and later units fail with the writer-closed error.
- **Why:** a replayed unit is compared with its first result by `!=`. A unit that returns a cursor or commits works until a later unit of its batch fails, which is rare in tests and normal in a Crawl, and the Crawl then ends `write_failed`.
- *Alternative:* an allowlist of value types walked recursively. It refuses every new record type until it is listed, and costs a walk per unit. Rejected.

### D7. Schema conventions that a test checks
- **In short:** two guards over `linx schema`: a column whose name ends in `_at` has the format `timestamp`, and a column `<x>_message` has a column `<x>` with values.
- Only one direction for `_at`: a timestamp may have another name, such as `pages.last_modified`, which is named after its header.
- CONTRIBUTING says which conventions tests check and which only review checks, as `docs/schema.md` does.
- **Why:** each mistake passes every test today and leaves the column without its CHECK and its Format or Values cell, so an agent that queries it with SQL loses the format. Both rules read only the declared schema, so the guards are cheap and cannot drift.
- *Alternative:* guard every ADR-0005 naming rule, such as `is_` for booleans and the unit suffixes. Those rules have exceptions a test cannot tell from mistakes, so review keeps them. Rejected.

### D8. SQL lives in the store, the `--where` language in `openlinx.query`
- **In short:** the tokenizer, the parser and the syntax tree of `--where` are in `openlinx.query`, pure and tested at seam 4; the compiler to SQLAlchemy Core and every statement are in `openlinx.store`, under `openlinx.store.query`; the Query Service calls store functions.
- The sqlalchemy guard says "SQL lives in openlinx.store: build the statement there (openlinx.store.query for --where) and call it from your service".
- *Alternative:* the compiler in `openlinx.query` beside its parser, with the guard widened to it. SQL would then live in two packages, and the guard's rule would read "the store, plus whatever asked". Rejected.

### D9. The Crawl's input is checked by `plan_crawl`
- **In short:** `plan_crawl(request, tables=None)` checks everything a caller gives it, so the CLI adapter only maps flags and a service call without the CLI validates the same way.
- **The module:** its interface is `CrawlRequest` (the Seed, the Workspace inputs, the settings given by table, `subdomains`, the command line and `secret_flags`, the argv tokens to redact) and the codes it raises. Behind it: the settings tables, precedence (a given value beats the file), the `subdomains` alias and its `option_conflict`, the fields' bounds, the secret settings, and which input a refused value came from.
- **Adapters:** the Typer adapter, which passes the values given on the command line; the test helper `crawl_result`, which passes plain values and builds no app; later the MCP server. Removing the module would put the registry, the conflict and the error mapping back into each adapter.
- **The tables:** `default_tables()` in `openlinx.services.settings` lists every built-in table by its `"module:Class"` reference, so `build_app` stays light; `plan_crawl` and `init_workspace` default to it. A change that adds a table registers it there.
- **A refused given value:** `load_settings` splits a validation error by its key: an error at a key the caller gave is that value's, raised as `invalid_value` (exit 2) with `details.key`; the others stay `settings_invalid` with `details.file`. Continuing a Crawl maps a refused override the same way. `Settings.table` names a table that is not registered instead of raising `StopIteration`.
- An import rule keeps `typer` and `openlinx.cli` out of `openlinx.services`, `.workspace`, `.store`, `.crawl`, `.extract` and `.output`.
- *Alternative:* a separate `build_crawl_request(given, tables)` that each adapter calls before `plan_crawl`. It is a second call to make in the right order, with no behaviour of its own. Rejected.
- *Alternative:* `default_tables()` in `openlinx.services.hooks`, beside `default_hooks()`. That module imports the extractors and the store, so `--help` would load them. Rejected.

### D10. An option that mirrors a setting matches its field
- **In short:** a guard over every Command checks that an option with a setting has the key's name (`-` for `_`), the field's default and the field's bounds as Click's `min` and `max`, and that every `[crawl]` field has an option; its message names where to add the option.
- Click keeps its own `min` and `max`, so `--help` loads no pydantic. Click refuses a bad flag as `invalid_value`, and the runner adds `details.key` from the option's setting, so a refused flag and a refused value given to a service have one shape.
- *Alternative:* build Click's bounds from the fields when the app is built. It loads pydantic on `--help`. Rejected.

### D11. A Page's Link elements are located by ordinal
- **In short:** `locate_links(tree, links)` takes every Link of the Page in order (`PageInput.links`, ordinals 1 to n) and returns a mapping from ordinal to a frozen `LocatedLink(element, placing)`; given anything else, it raises `ValueError("pass every Link of the Page; filter after locating")`.
- **Why:** it pairs references with Links by element, attribute, type and raw value in document order, so a subset pairs a Link with an earlier element of the same URL, and a handler would write the wrong anchor text and position.
- *Alternative:* keep each reference's element during the one walk, in `PageInput`. It removes the second walk but puts parser nodes into a record that must never cross `026`'s process boundary. Rejected.

### D12. One Link type table
- **In short:** `LINK_TYPES` in `openlinx.store.records` maps each `LinkType` to its `requested` value (`followed`, `resource` or none) and its `sources`: the `(LinkElement, LinkAttribute)` pairs it is found in, and whether a header gives it.
- **What reads it:** the follow rule and `RESOURCE_LINK_TYPES` derive from `requested`; Link discovery builds its element selectors from `sources` and narrows an element's tag through them, so `DiscoveredLink.element` is `LinkElement | None` and `attribute` is `LinkAttribute | None`, checked by mypy. The conditions stay in discovery: which `rel` gives which type, and which parent makes a `<source>` video or audio.
- `LinkElement` and `LinkAttribute` move beside `LinkType`; the `links` CHECKs read them.
- `discovered_link`, the one constructor that applies the follow rule, moves beside `DiscoveredLink` in `openlinx.crawl.references`, and the factory guard names a `DiscoveredLink(...)` built elsewhere.
- **Guards:** `030`'s element guard compares the `(element, attribute)` pairs that discovery gives on its fixture with the table's pairs, and the table's elements and attributes with the two Literals; a docs check compares the Requested column of `docs/crawling.md`'s table with `requested`.
- **Why in the store:** the store may import only `openlinx.crawl.urls`, and its CHECKs and its upsert read the values.
- *Alternative:* the sources in `openlinx.crawl.pages.links` and the follow rule in the store. Discovery's knowledge would stay in discovery, but the guards would read two modules for one table. Rejected.

### D13. Package interface lists are complete
- **In short:** a guard checks that every name imported from `openlinx.crawl.<package>.<module>` outside that package is listed in the package's docstring, and its message names the docstring to edit.
- `docs/architecture.md` says where a Link's element comes from: `locate_links(tree, page.links)`.
- **Why:** CONTRIBUTING makes these lists the only statement of a package's interface, and they leave out names other packages already import, such as `prepare_page` and `locate_links`; a contributor who trusts them takes the names for internal ones and writes the walk again.
- *Alternative:* `__all__` in each module. It states each module's names, not the package's interface, and nothing reads it in a package that is never star-imported. Rejected.

### D14. `linx commands` describes what the tool does
- **In short:** each option gives `min` and `max` (null when unbounded), hidden options are left out, and `environment` lists no variable.
- **Why:** the MCP server and the Skill build their input schemas from this description, so a missing bound lets a client send a value the tool refuses, a hidden option becomes a public input, and a listed variable that no session reads sends an agent behind a proxy straight past it.
- *Alternative:* keep the proxy entry and read the variables now with `trust_env`. The proxy's settings, overrides and redaction belong to the fetch policy, and half of it would be a contract to keep. Rejected.

### D15. Guards fail with the fix
- **In short:** every guard asserts with a message `<rule>: <fix>`; ruff selects `PGH004`, so a `# noqa` names its rule; a guard keeps the `noqa: TID251` lines to the three that need Click and the raw streams; `_declare` refuses a repeated code and a code whose level and exit code disagree; the docs-link guard covers AGENTS.md, CONTEXT.md, ROADMAP.md and the fixture site's README, anchors included.
- **Why:** AGENTS.md promises that a check's message says the fix, and an agent reads the failure, not the guard's source. A bare `# noqa` silences the banned-API rules in one keystroke. A repeated code is listed twice and the warning log keeps the last; an error code without an exit code fails only on its error path. AGENTS.md's links and anchors are the ones agents follow first.
- *Alternative:* a shared helper module that formats every guard's message. The guards differ in what they list, and one f-string each is as short. Rejected.

### D16. Test seams
- **In short:** the pure politeness and pause formulas (`global_cap`, `watchdog_seconds`, `pause_after`, `probe_times`, `BlockingRuns`) are tested at seam 4, table-driven, beside the service tests of the same rules.
- The race of a skip that a raise overtook is driven through `crawl_result` with `FakeFetcher`'s page delays on `FakeClock`, and the test checks that the handler saw the URL twice, so it fails if the timing stops staging the race. `Outcomes` stays off the seam list.
- **Why:** the formulas are specified tables whose values a service test shows only one at a time, so a table at seam 4 is the cheaper and the clearer proof; the race test pins a real double count, and the outcome pipeline's internals are its only setting today.
- *Alternative:* delete the formula tables and keep the service tests. The tables would lose their checks of the edges. Rejected.
- Seams of this change: 1 (`linx commands`), 2 (`plan_crawl`, the writer, the settings loader), 3+6 (hook failures), 4 (the stop flag, the extractor check, `locate_links`, the formulas), 6 (the schema guards).

## Risks / Trade-offs

- **The value-equality check misses a nested identity field:** a frozen dataclass compares by value even when a field holds a cursor. → The replay comparison still catches it, as today; the check targets the common shapes.
- **A NaN result** compares unequal to itself, so its replay fails. → A unit that returns a float is rare; the replay error names the unit.
- **Two bounds per option** (Click and the field). → D10's guard keeps them equal.
- Guards named after no scenario, and the failure class each guards:
  - `test_a_stop_flag_set_off_its_loop_is_refused`: an off-loop set that wakes no waiter.
  - `test_the_default_page_settings_pickle`: an extractor or config that `026`'s workers cannot load.
  - `test_an_extractor_whose_function_is_not_module_level_cannot_be_built`: an extractor that works in process and fails in every `026` worker.
  - `test_an_error_that_cannot_be_printed_costs_only_the_extractor_s_output`: a hook failure whose report fails the URL.
  - `test_an_error_raised_in_a_library_points_at_the_extractor_s_line`: a hook failure that points into the library instead of the hook.
  - `test_every_table_is_declared_in_the_schema_module`: a table missing from the contract.
  - `test_every_name_used_across_a_package_is_listed`: a hidden package interface.
  - `test_mirrored_options_match_their_fields`: a flag whose default or bounds differ from its setting.
  - `test_only_the_streams_and_click_compat_suppress_tid251`: a banned API silenced.
  - `test_link_type_table_matches_the_docs`: the docs' Requested column out of step.
