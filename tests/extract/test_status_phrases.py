"""The reason phrase table against the checked-in IANA registry snapshot (030-add-page-data D19)."""

import csv
import re
from pathlib import Path

from spider.extract.status_phrases import STATUS_PHRASES

_SNAPSHOT = Path(__file__).resolve().parents[2] / "scripts" / "http-status-codes-1.csv"


def test_the_phrase_table_is_the_registry_snapshot() -> None:
    with _SNAPSHOT.open(encoding="utf-8", newline="") as snapshot:
        rows = list(csv.DictReader(snapshot))
    # An annotation such as (OBSOLETED) or a temporary registration's terms is no part of the
    # phrase, and a code the registry leaves unassigned or unused has none.
    registered = {
        int(row["Value"]): re.sub(r"\s*\(.*\)$", "", row["Description"])
        for row in rows
        if row["Value"].isdigit() and row["Description"] not in ("Unassigned", "(Unused)")
    }

    assert registered == STATUS_PHRASES
