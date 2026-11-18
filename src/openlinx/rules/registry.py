"""Collect the Rules in catalogue order."""

from openlinx.rules.model import Rule
from openlinx.rules.response_codes import RULES as RESPONSE_CODE_RULES

# Follow the spec's order of categories and the order of each category's table.
RULES: tuple[Rule, ...] = RESPONSE_CODE_RULES
