"""Rules evaluated over a crawl file (040-add-rules D1, D15)."""

from pathlib import Path

import orjson

from spider.rules.model import Rule
from spider.store.reading import reading
from spider.store.records import AffectedUrl


def evaluate_rule(crawl_file: Path, rule: Rule) -> list[AffectedUrl]:
    """The Affected URLs that the Rule's query returns over the file's stored rows."""
    with reading(crawl_file) as connection:
        rows = connection.exec_driver_sql(rule.reproduce_sql).all()
    return [
        AffectedUrl(url_id=url_id, detail=None if detail is None else orjson.loads(detail))
        for url_id, detail in rows
    ]
