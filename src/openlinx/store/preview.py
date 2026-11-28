"""Recognise the shipped pre-Health Rules preview without changing its schema."""

from hashlib import sha256

from sqlalchemy import Connection, select

from openlinx.json_numbers import decode_json_object
from openlinx.store.schema import crawl, rules

PREVIEW_PLACEHOLDER_IDS = ("h2-missing", "low-word-count", "url-parameters")
PREVIEW_NO_ROWS = "SELECT id AS url_id, NULL AS detail FROM urls WHERE 0"
_PREVIEW_RULE_IDS = frozenset(
    (
        "canonical-to-non-indexable",
        "h1-missing",
        "http-url",
        "internal-3xx",
        "internal-4xx",
        "internal-5xx",
        "internal-blocked-by-robots-txt",
        "internal-no-response",
        "meta-description-missing",
        "noindex",
        "redirect-chain",
        "redirect-loop",
        "title-duplicate",
        "title-missing",
        "title-too-long",
        *PREVIEW_PLACEHOLDER_IDS,
    )
)

HEALTH_COLUMNS = (
    crawl.c.health_score.name,
    crawl.c.health_internal_page_count.name,
    crawl.c.health_affected_page_count.name,
    crawl.c.health_calculated_at.name,
)

# Both journal modes of the 18fa7640 producer wrote the same schema version as the
# current tool. Match its stored DDL (tables, views and indexes) independently of
# tool version or the presence of any one Rule. The producer fixtures exercise it.
_PREVIEW_SCHEMA_SHA256 = "6728a195979aad5243019791d55a08311e18428b3be5aba2d59700a046915e66"
_SCHEMA_SQL = "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type, name"
_METADATA = select(crawl.c.schema_version, crawl.c.config)
_RULE_QUERIES = select(rules.c.id, rules.c.reproduce_sql)


def missing_health_columns(connection: Connection) -> tuple[str, ...]:
    present: set[str] = set(
        connection.exec_driver_sql("SELECT name FROM pragma_table_info(?)", (crawl.name,)).scalars()
    )
    return tuple(name for name in HEALTH_COLUMNS if name not in present)


def is_historical_preview(connection: Connection, missing_health: tuple[str, ...]) -> bool:
    """Require the pre-Health layout and both snapshots of the original 18-Rule catalogue."""
    if missing_health != HEALTH_COLUMNS:
        return False
    if connection.exec_driver_sql("PRAGMA user_version").scalar_one() != 1:
        return False
    ddl = "\n".join(connection.exec_driver_sql(_SCHEMA_SQL).scalars())
    if sha256(ddl.encode()).hexdigest() != _PREVIEW_SCHEMA_SHA256:
        return False
    version, config = connection.execute(_METADATA).one()
    if version != 1:
        return False
    try:
        recorded = decode_json_object(config).get("rules")
    except ValueError:
        return False
    if not isinstance(recorded, dict) or recorded.keys() != _PREVIEW_RULE_IDS:
        return False
    queries = connection.execute(_RULE_QUERIES).all()
    return {row.id for row in queries} == _PREVIEW_RULE_IDS and all(
        row.reproduce_sql == PREVIEW_NO_ROWS for row in queries if row.id in PREVIEW_PLACEHOLDER_IDS
    )
