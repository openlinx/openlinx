"""The Rule model (040-add-rules, rules)."""

from dataclasses import dataclass

from spider.store.records import AppliesTo, IssueType, Priority, RuleCategory


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
