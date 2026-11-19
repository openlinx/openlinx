"""Evaluate catalogue Rules and materialise their Affected URLs in the Crawl."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import orjson
from sqlalchemy import Connection, Integer, Text, bindparam, delete, insert, literal, select, text

from openlinx.rules.model import Rule
from openlinx.store.reading import reading
from openlinx.store.records import AffectedUrl
from openlinx.store.schema import affected_urls, rules
from openlinx.store.writer import Unit


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """Run the catalogue Rule's query through a read-only connection."""
    with reading(crawl_file) as connection:
        rows = connection.exec_driver_sql(rule.reproduce_sql).all()
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in rows
    ]


_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id).where(rules.c.enabled == 1)


def affected_urls_unit(rule: Rule) -> Unit[None]:
    """Replace one Rule's result atomically, including when its new result is empty."""
    # text() treats :name as a parameter even inside SQL literals. Preserve the catalogue
    # query verbatim and end a trailing line comment before SQLAlchemy closes the subquery.
    sql = rule.reproduce_sql.replace(":", "\\:") + "\n"
    found = text(sql).columns(url_id=Integer, detail=Text).subquery()
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def replace_rows(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return replace_rows


def _enabled_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(connection.scalars(_ENABLED))


class _IssueWriter(Protocol):
    async def run_async[T](self, unit: Unit[T]) -> T: ...


async def materialise_issues(writer: _IssueWriter, units: Mapping[str, Unit[None]]) -> None:
    """Run the installed Rule units enabled by this Crawl's snapshot."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule_id, unit in units.items():
        if rule_id in enabled:
            await writer.run_async(unit)
