"""Compare a Crawl's final Rule results with its recorded reproducing SQL."""

import json
from operator import itemgetter
from pathlib import Path
from typing import Any

from tests.support.crawls import query


def assert_rule_results(
    file: Path, rule_id: str, expected: list[tuple[str, dict[str, Any] | None]]
) -> None:
    """Check details in URL order, including a genuine SQL NULL when the Rule has none."""
    recorded = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,))
    assert len(recorded) == 1, f"Expected a recorded Rule for {rule_id}"
    [(sql,)] = recorded

    urls = dict(query(file, "SELECT id, url FROM urls"))
    reproduced = [
        (urls[url_id], json.loads(raw) if raw is not None else None)
        for url_id, raw in query(file, sql)
    ]
    reproduced.sort(key=itemgetter(0))
    stored_results = query(
        file,
        "SELECT urls.url, a.detail FROM affected_urls AS a "
        "JOIN urls ON urls.id = a.url_id WHERE a.rule_id = ? ORDER BY urls.url",
        (rule_id,),
    )
    materialised = [
        (url, json.loads(raw) if raw is not None else None) for url, raw in stored_results
    ]
    assert reproduced == expected, (reproduced, expected)
    assert materialised == expected, (materialised, expected)
