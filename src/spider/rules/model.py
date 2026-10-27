"""The Rule model (040-add-rules D1, D12)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory
from spider.store.rule_queries import rule_not_found

type ThresholdUnit = Literal["characters", "pixels", "words", "kilobytes", "hops"]
# The views that a Rule's query joins (design D19).
type Population = Literal["internal_urls", "analysed_pages", "indexable_pages"]

# The spec's applies_to names no Indexable population: Indexable-only narrows internal_pages.
_APPLIES_TO: Mapping[Population, AppliesTo] = {
    "internal_urls": "internal_urls",
    "analysed_pages": "internal_pages",
    "indexable_pages": "internal_pages",
}

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
    population: Population
    description: str
    why_it_matters: str
    how_to_fix: str
    # The only form of the Rule's condition (design D1, D15).
    reproduce_sql: str
    thresholds: tuple[Threshold, ...] = ()

    @property
    def applies_to(self) -> AppliesTo:
        return _APPLIES_TO[self.population]


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguredRule:
    """A Rule with its [rules.<id>] settings: whether it runs, and its threshold values."""

    rule: Rule
    enabled: bool
    thresholds: Mapping[str, int]


def find_rule(catalogue: Sequence[Rule], rule_id: str) -> Rule:
    found = next((rule for rule in catalogue if rule.id == rule_id), None)
    if found is None:
        raise rule_not_found(rule_id, [rule.id for rule in catalogue])
    return found
