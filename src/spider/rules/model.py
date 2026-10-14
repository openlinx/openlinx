"""The Rule model (040-add-rules D1, D12)."""

from dataclasses import dataclass
from typing import Literal

from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory

type ThresholdUnit = Literal["characters", "pixels", "words", "kilobytes", "hops"]

# The query of a Rule registered before the slice of its condition, until that slice.
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
    # The only form of the Rule's condition (design D1, D15).
    reproduce_sql: str
    thresholds: tuple[Threshold, ...] = ()
