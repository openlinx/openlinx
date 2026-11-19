"""Define the catalogue query the Store accepts and diagnostics for unavailable Rules."""

from collections.abc import Sequence
from difflib import get_close_matches
from typing import Protocol

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import RULE_NOT_FOUND
from openlinx.output.diagnostics import OpenLinxError


class RuleQuery(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def reproduce_sql(self) -> str: ...


def rule_not_found(rule_id: str, known: Sequence[str]) -> OpenLinxError:
    return OpenLinxError(
        RULE_NOT_FOUND,
        f"No Rule with the id {rule_id} is recorded in this Crawl.",
        hint=(
            f"Inspect the Crawl's rules table for recorded ids. Use {COMMAND_NAME} rules list "
            "to see the installed catalogue."
        ),
        details={"id": rule_id, "suggestions": get_close_matches(rule_id, known)},
    )


def rule_not_computable(rule_id: str) -> OpenLinxError:
    return OpenLinxError(
        RULE_NOT_FOUND,
        f"This version of {COMMAND_NAME} cannot compute the recorded Rule {rule_id} live.",
        hint=f"Run the Rule's reproduce_sql from this Crawl's rules table with {COMMAND_NAME} sql.",
        details={"id": rule_id},
    )
