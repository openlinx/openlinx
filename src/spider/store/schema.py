"""The declared public schema (015-add-crawl-store D6; 018-add-schema-conventions D2, D3)."""

from typing import Any, Literal, get_args, get_origin

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
)

from spider.store.records import (
    CrawlMode,
    CrawlState,
    DiscoveredVia,
    FetchError,
    FetchState,
    JournalMode,
    ParseError,
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
                    column.in_(column.info["values"]), name=f"{table_name}_{column.name}_values"
                )
            )
        if isinstance(column.type, Flag):
            checks.append(
                CheckConstraint(column.in_([0, 1]), name=f"{table_name}_{column.name}_flag")
            )
    return checks


def public_tables() -> list[Table]:
    """The declared tables but the internal ones, whose names start with an underscore."""
    return [table for table in metadata.tables.values() if not table.name.startswith("_")]


def public_table(name: str, *columns: Column[Any], comment: str, change: int) -> Table:
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
    )


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
        comment="How the URL was first found: seed, or the Link type.",
        info={"values": literal_values(DiscoveredVia)},
    ),
    Column(
        "found_on_url_id",
        Integer,
        ForeignKey("urls.id"),
        comment="The URL whose response first revealed this one; NULL for Seeds.",
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
        comment="The text of the Page's first title element, whitespace-normalised; NULL "
        "without one, or when the Page is not analysed.",
    ),
    Column(
        "title_1_length",
        Integer,
        comment="The length of title_1 in Unicode code points; NULL exactly when title_1 is.",
    ),
    Column(
        "title_2",
        Text,
        comment="The text of the Page's second title element, whitespace-normalised; NULL "
        "without one, or when the Page is not analysed.",
    ),
    Column(
        "title_count",
        Integer,
        comment="The number of title elements outside svg and math; NULL when the Page is not "
        "analysed.",
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
