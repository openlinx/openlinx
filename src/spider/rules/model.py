"""The Rule model (040-add-rules D1, D12)."""

from dataclasses import dataclass
from typing import Literal

from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory

type ThresholdUnit = Literal["characters", "pixels", "words", "kilobytes", "hops"]


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
    thresholds: tuple[Threshold, ...] = ()
