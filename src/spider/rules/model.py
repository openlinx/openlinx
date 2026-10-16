"""The Rule model (040-add-rules D1, D12)."""

import difflib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from spider.naming import APP_NAME
from spider.output.codes import RULE_NOT_FOUND
from spider.output.diagnostics import SpiderError
from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory

type ThresholdUnit = Literal["characters", "pixels", "words", "kilobytes", "hops"]
# The views that a Rule's query joins (design D19).
type Population = Literal["internal_urls", "analysed_pages", "indexable_pages"]

# The Health Score counts the Indexable Pages among the Internal Pages.
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


def find_rule(catalogue: Sequence[Rule], rule_id: str) -> Rule:
    found = next((rule for rule in catalogue if rule.id == rule_id), None)
    if found is None:
        raise rule_not_found(rule_id, [rule.id for rule in catalogue])
    return found


def rule_not_found(rule_id: str, known: Sequence[str]) -> SpiderError:
    return SpiderError(
        RULE_NOT_FOUND,
        f"No Rule has the id {rule_id}.",
        hint=f"{APP_NAME} rules list lists every Rule id.",
        details={"id": rule_id, "suggestions": difflib.get_close_matches(rule_id, known)},
    )


def rule_not_computable(rule_id: str) -> SpiderError:
    # The tool never runs a file's own SQL (D15): only the user may choose to.
    return SpiderError(
        RULE_NOT_FOUND,
        f"This version of {APP_NAME} cannot compute the Rule {rule_id} live: another version "
        "made this Crawl.",
        hint=f"Run the Rule's reproduce_sql, in the Crawl's rules table, with {APP_NAME} sql.",
        details={"id": rule_id},
    )
