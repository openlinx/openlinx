"""The declared public schema (015-add-crawl-store D6; 018-add-schema-conventions D2)."""

from typing import Any, get_args

from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, Text, or_

from spider.store.records import CrawlMode, CrawlState, JournalMode
from spider.store.types import Flag, Json, Timestamp

# Stays 1 until the first schema change after v0.1, which brings migrations (design D5).
SCHEMA_VERSION = 1
CRAWL_MODES = list(get_args(CrawlMode.__value__))
CRAWL_STATES = list(get_args(CrawlState.__value__))
JOURNAL_MODES = list(get_args(JournalMode.__value__))

metadata = MetaData()


def _checks(table: str, columns: tuple[Column[Any], ...]) -> list[CheckConstraint]:
    checks = []
    for column in columns:
        if "values" in column.info:
            allowed = column.in_(column.info["values"])
            condition = or_(column.is_(None), allowed) if column.nullable else allowed
            checks.append(CheckConstraint(condition, name=f"{table}_{column.name}_values"))
        if isinstance(column.type, Flag):
            checks.append(CheckConstraint(column.in_([0, 1]), name=f"{table}_{column.name}_flag"))
    return checks


def public_table(name: str, *columns: Column[Any], comment: str, change: int) -> Table:
    """The one way to declare a public table: it adds the CHECKs its columns' values call for."""
    return Table(
        name, metadata, *columns, *_checks(name, columns), comment=comment, info={"change": change}
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
