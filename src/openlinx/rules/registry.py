"""Collect the Rules in catalogue order."""

from openlinx.rules.content import RULES as CONTENT_RULES
from openlinx.rules.headings import RULES as HEADING_RULES
from openlinx.rules.meta_descriptions import RULES as META_DESCRIPTION_RULES
from openlinx.rules.model import Rule
from openlinx.rules.response_codes import RULES as RESPONSE_CODE_RULES
from openlinx.rules.titles import RULES as TITLE_RULES
from openlinx.rules.urls import RULES as URL_RULES

# Follow the spec's order of categories and the order of each category's table.
RULES: tuple[Rule, ...] = (
    *RESPONSE_CODE_RULES,
    *TITLE_RULES,
    *META_DESCRIPTION_RULES,
    *HEADING_RULES,
    *CONTENT_RULES,
    *URL_RULES,
)
