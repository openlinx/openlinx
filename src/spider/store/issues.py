"""Rules run over a crawl file, and the pass that stores their Issues (040-add-rules D5, D15)."""

from collections.abc import Callable, Sequence
from pathlib import Path

import orjson
from sqlalchemy import Connection, Integer, Text, bindparam, delete, insert, literal, select, text

from spider.rules.model import Rule
from spider.store.reading import reading
from spider.store.records import AffectedUrl
from spider.store.schema import affected_urls, rules
from spider.store.writer import CrawlWriter


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """The Affected URLs that the Rule's query returns over the file's stored rows."""
    with reading(crawl_file) as connection:
        rows = connection.execute(text(rule.reproduce_sql)).all()
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in rows
    ]


_DELETE = delete(affected_urls).where(affected_urls.c.rule_id == bindparam("rule_id"))
_ENABLED = select(rules.c.id).where(rules.c.enabled == 1)


def affected_urls_unit(rule: Rule) -> Callable[[Connection], None]:
    """A unit that replaces the Rule's rows in affected_urls with those its query returns."""
    found = text(rule.reproduce_sql).columns(url_id=Integer, detail=Text).subquery()
    statement = insert(affected_urls).from_select(
        ["rule_id", "url_id", "detail"], select(literal(rule.id), found.c.url_id, found.c.detail)
    )

    def unit(connection: Connection) -> None:
        connection.execute(_DELETE, {"rule_id": rule.id})
        connection.execute(statement)

    return unit


async def materialise_issues(writer: CrawlWriter, catalogue: Sequence[Rule]) -> None:
    """The post-crawl pass: the Rules that the Crawl's rules table marks enabled (D5, D6)."""
    enabled = await writer.run_async(_enabled_rule_ids)
    for rule in catalogue:
        if rule.id in enabled:
            await writer.run_async(affected_urls_unit(rule))


def _enabled_rule_ids(connection: Connection) -> frozenset[str]:
    return frozenset(connection.execute(_ENABLED).scalars())
