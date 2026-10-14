# Functional core, frozen records and Protocols

The project's own way of writing code has so far lived only in the code. Lint, strict types, coverage, the dependency allowlist and the naming and startup tests hold the generic standards, but nothing says which shapes the code takes. A new contributor, or a coding agent, would bring their own, and agents default to class hierarchies. `020-add-crawl-core` adds more code than any change before it, so the paradigm is written down before it starts.

The code already follows it. Measured on `main` at f5abc9e (2026-10-11), `src/spider` has:
- 123 top-level functions against 67 methods
- 24 dataclasses, all frozen
- two Protocols, `Clock` and `Reporter`, passed as parameters
- no class hierarchy of its own, only framework base classes
- stateful classes only where the state is inherent: `Output`, `CrawlWriter`, `CliReporter`, `SystemClock`, `Collected` and `SettingsTables`
- a median of 46 non-blank lines per module (p90 127; the largest is `store/writer.py` at 366), and of 6 lines per function (p90 21)

## Decisions

- **Logic lives in pure functions.** A module's logic is in module-level functions that take values and return values. I/O stays at the edges: the CLI adapters read arguments and write output, the services put the steps together, and the store modules run SQL.
- **Data lives in frozen records:** `@dataclass(frozen=True)`. A record may have a constructor (`Diagnostic.of`) and a pure conversion (`to_json()`), but nothing that changes state or does I/O. A changed value is a new record (`dataclasses.replace`).
  - **`slots=True` is required for records made per URL, Page or Link:** handler results, store rows, and anything sent to `026`'s parse pool. A Crawl makes millions of them. A slotted record of six integers takes 88 bytes instead of 128 on Python 3.12 and 3.14. Slotted frozen records pickle, also through a `spawn` process pool, on 3.12, 3.13 and 3.14 (checked 2026-10-11). Other records may use slots, but need not. Two traps rule out slots for a record that needs them: on 3.12, a method of a slotted dataclass cannot call `super()` without arguments, and `functools.cached_property` fails on every version.
  - **`kw_only=True` is required for a record with more than three fields,** so a call site names every value and adding a field cannot shift the others. `NewCrawl`, with 10 fields, is such a record. Existing records adopt it when a change touches them, with no sweep.
  - **`msgspec.Struct` with `frozen=True` is the record kind for page preparation's per-response records, which cross `026`'s process pool, and for records that define a JSON document:** `020`'s `DiscoveredLink`, `PageInput`, extractor outputs and page-preparation record, and `050`'s `SummaryModel`. A Struct is slotted by nature, and takes `kw_only=True` above three fields like any record. Every other record stays a frozen dataclass, including page preparation's settings snapshot and the `ScopeRules` in it: the snapshot reaches each worker once, not with every response, so the speed of a Struct buys nothing there. The reason, measured on a 10-field Link record (Python 3.12 and 3.14, msgspec 0.22, 2026-10-11): a Struct is made in about 200 ns against 910 ns for a slotted dataclass, and 466 of them pickle and unpickle in about 0.7 ms against 1.6–1.9 ms, at 23.5 KB against 13.1 KB.
- **Dependencies come in as parameters typed by a Protocol:** the clock, the Reporter, and from `020` the Fetcher. A function or class receives what it uses. There are no module-level singletons and no subclassing to override behaviour. When a whole run needs many dependencies, they travel together in one frozen context record.
  - **A bounded memo of a pure function is not module-level state:** `functools.lru_cache(maxsize=N)` on a function whose result depends only on its arguments changes nothing a caller can see, so it is allowed. It always has a bound, so never `maxsize=None` or `functools.cache`, and a one-line comment at the decorator says why it pays. The first is `020`'s IDN host encoder in `spider.crawl.urls`: encoding an IDN host costs about 51 µs per URL, and on a `.рф` site every internal URL has one.
- **A class with state only where the state is inherent:** a connection, a stream, a queue, a thread or a watchdog. Such a class keeps a small public surface, keeps its state in a few private attributes, and moves any logic that does not touch its state into module functions.
  - `CrawlWriter` is the largest. It has 25 methods: `__init__`, the 8 public ones (`run`, `run_async`, `submit`, `submit_async`, `flush`, `close`, `__enter__`, `__exit__`) and 16 private helpers. That is a question for review, not a violation, because its state (a thread, a connection, a queue and a window of Futures) is inherent.
  - If it grows, it splits along that state. The batch and its replay (`_handle`, `_begin`, `_replay`, `_commit_if_due`, `_commit`) become functions over the connection and the open batch. The window (`_submit`, `_submit_without_blocking`, `_wait`, `_free`) becomes a small class of its own. `CrawlWriter` keeps the thread and the queue.
- **No inheritance hierarchies of our own.** Framework base classes are fine: `TyperGroup`, SQLAlchemy's `TypeDecorator`, `Exception` and `RuntimeError`, `Enum`, `IntEnum` and `StrEnum`, pydantic's `BaseModel` and `BaseSettings`, and msgspec's `Struct`. An error class subclasses a built-in exception directly. The one subclass of our own class is the per-app `AppGroup` that `build_app` makes of `SpiderGroup`, because Typer takes a class, not an instance, and each app needs its own settings tables.
- **pydantic only at the boundary:** settings tables and other external input that must be validated. It is never used for internal records, which are trusted once built. A pydantic model would validate every per-URL row again, and pydantic loads only with the settings.

## Considered Options

- **Classic OOP with class hierarchies:** behaviour overridden in subclasses, and state on long-lived objects. Rejected. It hides state and the order of calls, needs a subclass to make a test double, and spreads one behaviour over several classes. Pure functions over frozen records are tested with plain values.
- **pydantic models everywhere:** one model kind for input and internal data. Rejected. Validating per URL costs time at 500k URLs, it ties internal data to a boundary library, and dataclasses are already checked by mypy strict.
- **A strict third-party style linter as a CI gate:** rejected. Its default limits push towards smaller modules and classes than this style uses, so it would fight the code instead of guarding it. The ROADMAP Backlog item "Code quality checks" weighs ruff's complexity rules and a one-off audit instead.

## Consequences

- Tests use fakes through the Protocols, such as `FakeClock` and the collecting Reporter, never mocks of our own modules ([docs/testing.md](../testing.md)).
- Records cross `026`'s process pool by pickling, because they are frozen data with slots.
- `020` follows from this ADR:
  - `NormalizedUrl`, a type that only the normaliser makes
  - Crawl State changes guarded by one `TRANSITIONS` table
  - one frozen `CrawlContext` that carries a Crawl's dependencies
- `017`'s unit contract (its design D7) fits it: a unit returns values only, such as a number, a tuple or a frozen dataclass, so that a replay can compare its results.
- Review checks the parts that no test can:
  - a new class that holds state without needing to
  - a new hierarchy
  - a pydantic model inside the core
  - a per-URL record without slots
  - a memo without a bound, or without its one-line why
- [CONTRIBUTING.md](../../CONTRIBUTING.md) "Code style" holds the day-to-day rules that go with this ADR.
