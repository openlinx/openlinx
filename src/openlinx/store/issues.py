"""Evaluate Rules over the rows of a crawl file."""

from pathlib import Path

import orjson

from openlinx.rules.model import Rule
from openlinx.store.reading import reading
from openlinx.store.records import AffectedUrl


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """Run the catalogue Rule's query through a read-only connection."""
    with reading(crawl_file) as connection:
        rows = connection.exec_driver_sql(rule.reproduce_sql).all()
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in rows
    ]
