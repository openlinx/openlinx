"""Define the fixed catalogue metadata and query of a Rule."""

from dataclasses import dataclass
from typing import Literal

from openlinx.store.records import AppliesTo, IssueType, Priority, RuleCategory

type ThresholdUnit = Literal["characters", "pixels", "words", "kilobytes", "hops"]

# The catalogue can describe a Rule before its condition is available.
NO_ROWS = "SELECT id AS url_id, NULL AS detail FROM urls WHERE 0"


@dataclass(frozen=True, slots=True)
class Threshold:
    name: str
    default: int
    unit: ThresholdUnit


@dataclass(frozen=True, slots=True, kw_only=True)
class Rule:
    id: str
    category: RuleCategory
    issue_type: IssueType
    priority: Priority
    applies_to: AppliesTo
    description: str
    why_it_matters: str
    how_to_fix: str
    reproduce_sql: str
    thresholds: tuple[Threshold, ...] = ()
