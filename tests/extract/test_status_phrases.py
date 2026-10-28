"""The reason phrase table against the checked-in IANA registry snapshot (030-add-page-data D19)."""

import csv
from pathlib import Path

from spider.extract.status_phrases import STATUS_PHRASES

_SNAPSHOT = Path(__file__).resolve().parents[2] / "scripts" / "http-status-codes-1.csv"


def test_the_phrase_table_is_the_registry_snapshot() -> None:
    with _SNAPSHOT.open(encoding="utf-8", newline="") as snapshot:
        rows = list(csv.DictReader(snapshot))
    registered = {
        int(row["Value"]): row["Description"]
        for row in rows
        if row["Value"].isdigit() and row["Description"] not in ("Unassigned", "(Unused)")
    }

    assert set(STATUS_PHRASES) == set(registered)
    # An annotation such as (OBSOLETED) is no part of the phrase.
    assert all(registered[code].startswith(phrase) for code, phrase in STATUS_PHRASES.items())
