"""The catalogue (040-add-rules D4, D12; seam 4)."""

from typing import get_args

from spider.rules.registry import RULES
from spider.store.records import RuleCategory

CATEGORIES = get_args(RuleCategory.__value__)


def test_the_catalogue_keeps_the_category_order_and_unique_ids() -> None:
    places = [CATEGORIES.index(rule.category) for rule in RULES]
    ids = [rule.id for rule in RULES]

    assert (places == sorted(places), len(set(ids)) == len(ids)) == (True, True)


def test_thresholds_have_unique_names_and_defaults_of_at_least_0() -> None:
    names = [[threshold.name for threshold in rule.thresholds] for rule in RULES]
    defaults = [threshold.default for rule in RULES for threshold in rule.thresholds]

    assert (
        [rule_names for rule_names in names if len(set(rule_names)) != len(rule_names)],
        [default for default in defaults if default < 0],
    ) == ([], [])
