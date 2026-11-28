"""Present the versioned summary document as tables for people."""

from collections.abc import Mapping
from typing import Any

from openlinx.output.table import TitledTables


def summary_tables(summary: Mapping[str, Any]) -> TitledTables:
    """Lay out each summary section with the units and labels used by the Command."""
    health = summary["health_score"]
    return TitledTables(
        (
            ("Crawl", _pairs(summary["crawl"])),
            ("URL totals", _pairs(summary["totals"])),
            (
                "Status classes",
                [
                    {"URL scope": name, **counts}
                    for name, counts in summary["status_classes"].items()
                ],
            ),
            (
                "Indexability",
                _pairs(
                    {
                        "Indexable Pages": summary["indexability"]["indexable"],
                        "Non-Indexable Pages": summary["indexability"]["non_indexable"],
                    }
                ),
            ),
            ("Non-Indexable Pages by status", summary["indexability"]["by_status"]),
            ("Content types", summary["content_types"]),
            (
                "Crawl Depth",
                _pairs(
                    {
                        "Partial": summary["crawl_depth"]["partial"],
                        "Maximum": summary["crawl_depth"]["max"],
                    }
                ),
            ),
            ("Depth distribution", summary["crawl_depth"]["distribution"]),
            (
                "Response time (ms)",
                _pairs(
                    {
                        key: value
                        for key, value in summary["response_time_ms"].items()
                        if key != "histogram"
                    }
                ),
            ),
            ("Response time histogram (ms)", summary["response_time_ms"]["histogram"]),
            (
                "Health",
                _pairs(
                    {
                        "Health Score": health["score"],
                        "Internal Pages": health["internal_pages"],
                        "Affected Pages": health["affected_pages"],
                    }
                ),
            ),
            ("Issues", summary["issues"]["by_type_priority"]),
            ("Top Issues", summary["issues"]["top"]),
        )
    )


def _pairs(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, "value": value} for key, value in values.items()]
