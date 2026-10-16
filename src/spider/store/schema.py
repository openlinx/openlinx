"""The declared public schema (015-add-crawl-store D6; 018-add-schema-conventions D2, D3)."""

from typing import Any, Literal, get_args, get_origin

from sqlalchemy import (
    CheckConstraint,
    Column,
    ColumnElement,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Select,
    Table,
    Text,
    func,
    or_,
    select,
)
from sqlalchemy.sql.ddl import CreateView

from spider.naming import APP_NAME, SETTINGS_FILE_NAME
from spider.store.records import (
    AppliesTo,
    CrawlMode,
    CrawlState,
    DiscoveredVia,
    FetchError,
    FetchState,
    IssueType,
    JournalMode,
    ParseError,
    Priority,
    RobotsState,
    RuleCategory,
    SkipReason,
    StopReason,
)
from spider.store.types import Flag, Json, Timestamp


def literal_values(alias: Any) -> list[str]:
    """The values of a Literal alias in order, through unions of Literals and other aliases."""
    value = getattr(alias, "__value__", alias)
    if get_origin(value) is Literal:
        return list(get_args(value))
    return [item for member in get_args(value) for item in literal_values(member)]


# Stays 1 until the first schema change after v0.1, which brings migrations (design D5).
SCHEMA_VERSION = 1
CRAWL_MODES = literal_values(CrawlMode)
CRAWL_STATES = literal_values(CrawlState)
JOURNAL_MODES = literal_values(JournalMode)

metadata = MetaData()


def _checks(table_name: str, columns: tuple[Column[Any], ...]) -> list[CheckConstraint]:
    checks = []
    for column in columns:
        if "values" in column.info:
            checks.append(
                CheckConstraint(
                    _one_of(column, column.info["values"]),
                    name=f"{table_name}_{column.name}_values",
                )
            )
        if isinstance(column.type, Flag):
            checks.append(
                CheckConstraint(column.in_([0, 1]), name=f"{table_name}_{column.name}_flag")
            )
    return checks


def _one_of(column: Column[Any], values: list[str]) -> ColumnElement[bool]:
    # Never IN: SQLite builds an ephemeral index for an IN list of more than two values again
    # on every row of an executemany (ADR-0005).
    return or_(*(column == value for value in values))


def public_tables() -> list[Table]:
    """The declared tables but the internal ones, whose names start with an underscore."""
    return [table for table in metadata.tables.values() if not table.name.startswith("_")]


def public_table(
    name: str, *columns: Column[Any], comment: str, change: int, without_rowid: bool = False
) -> Table:
    """The one way to declare a public table: STRICT, with the CHECKs its columns' values call for.

    STRICT refuses the FLOAT and DOUBLE that `Float` and `Double` declare: a real number is `REAL`.
    """
    return Table(
        name,
        metadata,
        *columns,
        *_checks(name, columns),
        comment=comment,
        info={"change": change},
        sqlite_strict=True,
        sqlite_with_rowid=not without_rowid,
    )


def public_view(
    name: str, *columns: Column[Any], query: Select[Any], comment: str, change: int
) -> Table:
    """The one way to declare a public view: a query over the tables, with its columns declared.

    SQLite reports no NOT NULL and its own type names for a view's computed columns, so the
    declaration, which must name the query's columns in order, is what spider schema shows.
    """
    # Checked before CreateView, which adds the view to the metadata.
    if [column.name for column in query.selected_columns] != [column.name for column in columns]:
        raise TypeError(f"The view {name} declares other columns than its query selects.")
    view = CreateView(query, name, metadata=metadata).table
    for declared in columns:
        column = view.c[declared.name]
        column.type = declared.type
        column.nullable = declared.nullable
        column.comment = declared.comment
        column.info.update(declared.info)
    view.comment = comment
    view.info["change"] = change
    return view


crawl = public_table(
    "crawl",
    Column("id", Text, primary_key=True, comment="The crawl id."),
    Column(
        "crawl_mode",
        Text,
        nullable=False,
        comment="How the Crawl finds URLs.",
        info={"values": CRAWL_MODES},
    ),
    Column(
        "section_crawl",
        Flag,
        nullable=False,
        comment="1 for a Section Crawl, whose Scope is one part of a site, otherwise 0.",
    ),
    Column(
        "scope",
        Json,
        nullable=False,
        comment="The resolved Scope, as an object of mode, hosts, folder, include and exclude.",
    ),
    Column(
        "state",
        Text,
        nullable=False,
        comment="The Crawl State.",
        info={"values": CRAWL_STATES},
    ),
    Column("started_at", Timestamp, nullable=False, comment="When the Crawl started."),
    Column(
        "completed_at",
        Timestamp,
        comment="When the state became completed; NULL in every other state.",
    ),
    Column(
        "stop_reason",
        Text,
        comment="Why the Crawl ended early: max_urls, interrupt or requested for a stopped Crawl, "
        "seed_unreachable, site_unreachable or write_failed for a failed one; NULL while it "
        "runs and when it is completed.",
        info={"values": literal_values(StopReason)},
    ),
    Column(
        "command_argv",
        Json,
        nullable=False,
        comment="The command line as an array that starts with the command name, secrets redacted.",
    ),
    Column("cwd", Text, nullable=False, comment="The absolute folder the Command ran in."),
    Column(
        "settings_file",
        Text,
        comment="The absolute path of the settings file that was read, or NULL without one.",
    ),
    Column(
        "config",
        Json,
        nullable=False,
        comment="The resolved settings as an object of tables and keys, secrets redacted.",
    ),
    Column(
        "tool_version",
        Text,
        nullable=False,
        comment="The version of the tool that created the Crawl.",
    ),
    Column(
        "schema_version",
        Integer,
        nullable=False,
        comment="The schema version of this file, also stored as SQLite's user_version.",
    ),
    Column(
        "journal_mode",
        Text,
        nullable=False,
        comment="The SQLite journal mode the file was created with.",
        info={"values": JOURNAL_MODES},
    ),
    Column(
        "python_version",
        Text,
        nullable=False,
        comment="The Python version that created the Crawl.",
    ),
    Column(
        "platform",
        Text,
        nullable=False,
        comment="The operating system that created the Crawl, as Python describes it.",
    ),
    comment="The Crawl's metadata, in exactly one row.",
    change=15,
)

seeds = public_table(
    "seeds",
    Column(
        "position",
        Integer,
        primary_key=True,
        autoincrement=False,
        comment="The 1-based order in which the Seed was given.",
    ),
    Column("url", Text, nullable=False, comment="The Seed URL as given."),
    comment="The Seeds the Crawl started from, in the order they were given.",
    change=15,
)

urls = public_table(
    "urls",
    Column(
        "id",
        Integer,
        primary_key=True,
        comment="Row id, stable for the life of the crawl file; it grows in the order URLs are "
        "first recorded, and is the dispatch order within a Crawl Depth.",
    ),
    Column("url", Text, nullable=False, comment="The normalised URL, unique."),
    Column(
        "host",
        Text,
        nullable=False,
        comment="The URL's host in lower-case ASCII (IDNA) form; the key of the per-host "
        "politeness limits.",
    ),
    Column(
        "origin_id",
        Integer,
        ForeignKey("origins.id"),
        nullable=False,
        comment="The URL's origin: its scheme, host and port.",
    ),
    Column(
        "is_internal",
        Flag,
        nullable=False,
        comment="1 for an Internal URL, 0 for an External URL.",
    ),
    Column(
        "in_scope",
        Flag,
        nullable=False,
        comment="1 when the URL is inside the Scope, so it may be followed.",
    ),
    Column("crawl_depth", Integer, nullable=False, comment="Crawl Depth; 0 for Seeds."),
    Column(
        "discovered_via",
        Text,
        nullable=False,
        comment="How the URL was first found: seed, or the Link type; through a followed Link "
        "once one has reached it.",
        info={"values": literal_values(DiscoveredVia)},
    ),
    Column(
        "found_on_url_id",
        Integer,
        ForeignKey("urls.id"),
        comment="The URL whose response first revealed this one, through a followed Link once "
        "one has reached it; NULL for Seeds.",
    ),
    Column(
        "fetch_state",
        Text,
        nullable=False,
        comment="Frontier state: waiting, a response was recorded, no response, or not requested.",
        info={"values": literal_values(FetchState)},
    ),
    Column(
        "skip_reason",
        Text,
        comment="Why a skipped URL was not requested.",
        info={"values": literal_values(SkipReason)},
    ),
    Column(
        "blocked_by_robots_txt",
        Flag,
        comment="1 when robots.txt disallows the URL for the robots user-agent token (also "
        "with --ignore-robots), 0 when it allows it; NULL when not checked.",
    ),
    Column(
        "status_code",
        Integer,
        comment="HTTP status code of the URL's own response; NULL without a response.",
    ),
    Column(
        "fetch_error",
        Text,
        comment="Why no response is recorded for the URL.",
        info={"values": literal_values(FetchError)},
    ),
    Column("fetch_error_message", Text, comment="Human-readable detail of fetch_error."),
    Column(
        "content_type",
        Text,
        comment="The Content-Type response header as received; NULL without a response or "
        "without the header.",
    ),
    Column(
        "response_time_ms",
        Integer,
        comment="Time from sending the request to receiving the whole body.",
    ),
    Column("fetched_at", Timestamp, comment="UTC time of the request."),
    Column(
        "parsed",
        Flag,
        nullable=False,
        comment="1 when the response was parsed and its Links were found.",
    ),
    Column(
        "parse_error",
        Text,
        comment="Why parsing failed in whole or in part: a registered extractor failed (parsed "
        "stays 1), or nothing came out of page preparation (parsed = 0).",
        info={"values": literal_values(ParseError)},
    ),
    Column("parse_error_message", Text, comment="Human-readable detail of parse_error."),
    comment="One row for each distinct normalised URL of the Crawl; the frontier is its "
    "queued rows.",
    change=20,
)
Index(
    "urls_url",
    urls.c.url,
    unique=True,
    info={
        "description": "Recording a discovered URL once (ON CONFLICT (url)), and finding one "
        "URL's row."
    },
)
Index(
    "urls_crawl_depth_id",
    urls.c.crawl_depth,
    urls.c.id,
    sqlite_where=urls.c.fetch_state == "queued",
    info={
        "description": "The frontier: the next queued URLs of the open Crawl Depth, in id order."
    },
)

origins = public_table(
    "origins",
    Column("id", Integer, primary_key=True, comment="Row id."),
    Column(
        "origin",
        Text,
        nullable=False,
        comment="Scheme, host and port, for example https://site.test, with a default port left "
        "out; unique.",
    ),
    Column(
        "host",
        Text,
        nullable=False,
        comment="The origin's host in lower-case ASCII (IDNA) form.",
    ),
    Column(
        "is_internal",
        Flag,
        nullable=False,
        comment="1 when the origin's URLs are Internal URLs.",
    ),
    Column(
        "robots_state",
        Text,
        comment="Rules applied, everything allowed, or everything disallowed or unanswered; NULL "
        "while robots.txt has not been fetched, which happens before the first URL of the "
        "origin that the Scope does not skip and the URL limit does not refuse.",
        info={"values": literal_values(RobotsState)},
    ),
    Column(
        "robots_status_code",
        Integer,
        comment="Status code of the final robots.txt response; NULL without a response.",
    ),
    Column(
        "robots_fetch_error",
        Text,
        comment="Why the robots.txt request got no HTTP response; NULL when it got one, or "
        "while robots.txt has not been fetched.",
        info={"values": literal_values(FetchError)},
    ),
    Column(
        "robots_fetch_error_message",
        Text,
        comment="Human-readable detail of robots_fetch_error.",
    ),
    Column("robots_fetched_at", Timestamp, comment="UTC time robots.txt was last fetched."),
    Column("robots_txt", Text, comment="The robots.txt body as parsed, up to 512,000 bytes."),
    Column(
        "robots_crawl_delay_ms",
        Integer,
        comment="The Crawl-delay for the robots user-agent token; recorded, not applied.",
    ),
    Column(
        "robots_sitemaps",
        Json,
        comment="JSON array of the Sitemap: URLs in robots.txt; NULL while robots.txt has not "
        "been fetched.",
    ),
    comment="One row for each origin of a URL that the Crawl recorded.",
    change=20,
)
Index(
    "origins_origin",
    origins.c.origin,
    unique=True,
    info={
        "description": "Recording an origin once (ON CONFLICT (origin)), and finding an "
        "origin's row."
    },
)

pages = public_table(
    "pages",
    Column(
        "url_id",
        Integer,
        ForeignKey("urls.id"),
        primary_key=True,
        autoincrement=False,
        comment="The Page's URL.",
    ),
    Column(
        "address",
        Text,
        nullable=False,
        comment="The Page's URL for display: url_encoded_address with the host in Unicode and "
        "every percent-encoded UTF-8 sequence of a non-ASCII character decoded; percent-encoded "
        "ASCII characters stay encoded.",
    ),
    Column(
        "url_encoded_address",
        Text,
        nullable=False,
        comment="The Page's URL as the Crawl requested it, equal to urls.url: the host in IDNA "
        "(punycode) form and every non-ASCII character percent-encoded as UTF-8.",
    ),
    Column(
        "title_1",
        Text,
        comment="The text of the Page's first title element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed "
        "or its Page extractor failed.",
    ),
    Column(
        "title_1_length",
        Integer,
        comment="The length of title_1 in Unicode code points; NULL exactly when title_1 is.",
    ),
    Column(
        "title_2",
        Text,
        comment="The text of the Page's second title element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed "
        "or its Page extractor failed.",
    ),
    Column(
        "title_2_length",
        Integer,
        comment="The length of title_2 in Unicode code points; NULL exactly when title_2 is.",
    ),
    Column(
        "title_count",
        Integer,
        comment="The number of title elements without an svg, math or noscript ancestor; NULL "
        "when the Page is not analysed or its Page extractor failed.",
    ),
    Column(
        "meta_description_1",
        Text,
        comment="The content of the Page's first meta description, whitespace-normalised, the "
        "empty string for one without content; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "meta_description_1_length",
        Integer,
        comment="The length of meta_description_1 in Unicode code points; NULL exactly when "
        "meta_description_1 is.",
    ),
    Column(
        "meta_description_2",
        Text,
        comment="The content of the Page's second meta description, whitespace-normalised, the "
        "empty string for one without content; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "meta_description_2_length",
        Integer,
        comment="The length of meta_description_2 in Unicode code points; NULL exactly when "
        "meta_description_2 is.",
    ),
    Column(
        "meta_description_count",
        Integer,
        comment="The number of meta elements named description without an svg, math or "
        "noscript ancestor; NULL when the Page is not analysed or its Page extractor failed.",
    ),
    Column(
        "meta_keywords_1",
        Text,
        comment="The content of the Page's first meta keywords element, whitespace-normalised, "
        "the empty string for one without content; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "meta_keywords_1_length",
        Integer,
        comment="The length of meta_keywords_1 in Unicode code points; NULL exactly when "
        "meta_keywords_1 is.",
    ),
    Column(
        "h1_1",
        Text,
        comment="The text of the Page's first h1 element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "h1_1_length",
        Integer,
        comment="The length of h1_1 in Unicode code points; NULL exactly when h1_1 is.",
    ),
    Column(
        "h1_2",
        Text,
        comment="The text of the Page's second h1 element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "h1_2_length",
        Integer,
        comment="The length of h1_2 in Unicode code points; NULL exactly when h1_2 is.",
    ),
    Column(
        "h1_count",
        Integer,
        comment="The number of h1 elements without an svg, math or noscript ancestor; NULL when "
        "the Page is not analysed or its Page extractor failed.",
    ),
    Column(
        "h2_1",
        Text,
        comment="The text of the Page's first h2 element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "h2_1_length",
        Integer,
        comment="The length of h2_1 in Unicode code points; NULL exactly when h2_1 is.",
    ),
    Column(
        "h2_2",
        Text,
        comment="The text of the Page's second h2 element without an svg, math or noscript "
        "ancestor, whitespace-normalised; NULL without one, or when the Page is not "
        "analysed or its Page extractor failed.",
    ),
    Column(
        "h2_2_length",
        Integer,
        comment="The length of h2_2 in Unicode code points; NULL exactly when h2_2 is.",
    ),
    Column(
        "h2_count",
        Integer,
        comment="The number of h2 elements without an svg, math or noscript ancestor; NULL when "
        "the Page is not analysed or its Page extractor failed.",
    ),
    comment="One row for each Page of the Crawl: an Internal URL in the Scope whose response is "
    "an HTML document, whatever its status code.",
    change=30,
)
Index(
    "pages_address",
    pages.c.address,
    unique=True,
    info={
        "description": "Finding a Page by its display address, and the tie-breaker of keyset "
        "paging over Pages."
    },
)

rules = public_table(
    "rules",
    Column(
        "id",
        Text,
        primary_key=True,
        comment=f"The Rule id, as typed in {APP_NAME} rules show and {SETTINGS_FILE_NAME}.",
    ),
    Column(
        "category",
        Text,
        nullable=False,
        comment="The Rule's category.",
        info={"values": literal_values(RuleCategory)},
    ),
    Column(
        "issue_type",
        Text,
        nullable=False,
        comment="The Issue Type of the Rule's Issues.",
        info={"values": literal_values(IssueType)},
    ),
    Column(
        "priority",
        Text,
        nullable=False,
        comment="The Priority of the Rule's Issues.",
        info={"values": literal_values(Priority)},
    ),
    Column(
        "applies_to",
        Text,
        nullable=False,
        comment="The population the Rule is evaluated over.",
        info={"values": literal_values(AppliesTo)},
    ),
    Column("enabled", Flag, nullable=False, comment="1 when the Rule was evaluated in this Crawl."),
    Column(
        "thresholds",
        Json,
        nullable=False,
        comment="The effective thresholds, as an object of names to integers; {} for a Rule "
        "without thresholds.",
    ),
    Column("description", Text, nullable=False, comment="What the Rule checks."),
    Column("why_it_matters", Text, nullable=False, comment="Why its Issues matter."),
    Column("how_to_fix", Text, nullable=False, comment="How to fix its Issues."),
    Column(
        "reproduce_sql",
        Text,
        nullable=False,
        comment="The Rule's reproducing query: a read-only SELECT over this file that returns its "
        "Affected URLs as url_id and detail.",
    ),
    comment="One row for each Rule of the catalogue, with the configuration the Crawl was "
    "created with, which it uses throughout.",
    change=40,
)

affected_urls = public_table(
    "affected_urls",
    Column(
        "rule_id",
        Text,
        ForeignKey("rules.id"),
        primary_key=True,
        comment="The Rule that fired.",
    ),
    Column(
        "url_id",
        Integer,
        ForeignKey("urls.id"),
        primary_key=True,
        autoincrement=False,
        comment="The Affected URL.",
    ),
    Column(
        "detail",
        Json,
        comment="The measured values, as an object with the keys listed for the Rule; NULL "
        "when the Rule lists none.",
    ),
    comment="One row for each Rule and its Affected URL, written only by the post-crawl pass: "
    "the result of the last pass.",
    change=40,
    without_rowid=True,
)
Index(
    "affected_urls_url_id",
    affected_urls.c.url_id,
    info={"description": "The Issues of one URL, and the Health Score's count of affected Pages."},
)

issues = public_view(
    "issues",
    Column(
        "rule_id",
        Text,
        nullable=False,
        comment="The Rule that fired.",
        info={"references": "rules.id"},
    ),
    Column(
        "category",
        Text,
        nullable=False,
        comment="The Rule's category.",
        info={"values": literal_values(RuleCategory)},
    ),
    Column(
        "issue_type",
        Text,
        nullable=False,
        comment="The Issue Type of the Rule's Issues.",
        info={"values": literal_values(IssueType)},
    ),
    Column(
        "priority",
        Text,
        nullable=False,
        comment="The Priority of the Rule's Issues.",
        info={"values": literal_values(Priority)},
    ),
    Column(
        "affected_count",
        Integer,
        nullable=False,
        comment="The number of the Rule's rows in affected_urls.",
    ),
    # Grouped by the primary key's prefix, so the count reads affected_urls in key order.
    query=select(
        rules.c.id.label("rule_id"),
        rules.c.category,
        rules.c.issue_type,
        rules.c.priority,
        func.count().label("affected_count"),
    )
    .join_from(affected_urls, rules, affected_urls.c.rule_id == rules.c.id)
    .group_by(affected_urls.c.rule_id),
    comment="The Issues: one row for each Rule with at least one Affected URL, counted from "
    "affected_urls, so it holds the result of the last post-crawl pass.",
    change=40,
)


def _population(name: str, query: Select[Any], comment: str) -> Table:
    """The URL ids of a population, which a Rule's query joins (040-add-rules D19)."""
    return public_view(
        name,
        Column(
            "url_id",
            Integer,
            nullable=False,
            comment="A member of the population.",
            info={"references": "urls.id"},
        ),
        query=query,
        comment=comment,
        change=40,
    )


def _analysed() -> Select[Any]:
    return (
        select(pages.c.url_id)
        .join_from(pages, urls, pages.c.url_id == urls.c.id)
        .where(urls.c.parsed == 1)
    )


internal_urls = _population(
    "internal_urls",
    select(urls.c.id.label("url_id")).where(
        urls.c.is_internal == 1, urls.c.fetch_state.in_(("fetched", "error"))
    ),
    "The Internal URLs that were requested.",
)
analysed_pages = _population(
    "analysed_pages",
    _analysed(),
    "The Pages that were parsed, also when one of their extractors failed.",
)
# Narrowed to the indexable Pages once the store records Indexability.
indexable_pages = _population(
    "indexable_pages",
    _analysed(),
    "The analysed Pages that are indexable. The store records no Indexability yet, so it holds "
    "every analysed Page.",
)
