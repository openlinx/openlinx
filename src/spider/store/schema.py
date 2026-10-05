"""The declared public schema of a crawl file (design D6 of 015-add-crawl-store)."""

from sqlalchemy import Column, MetaData, Table, Text

from spider.store.types import Flag, Json, Timestamp

CRAWL_MODES = ["spider", "list", "sitemap"]
CRAWL_STATES = ["running", "stopped", "completed", "failed", "interrupted"]

metadata = MetaData()

crawl = Table(
    "crawl",
    metadata,
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
    comment="The Crawl's metadata, in exactly one row.",
    info={"change": 15},
)
