"""What the store needs of a Rule, and its errors: spider.rules sits above the store and passes
its Rules in (040-add-rules D15, D16)."""

import difflib
from collections.abc import Sequence
from typing import Protocol

from spider.naming import APP_NAME
from spider.output.codes import RULE_NOT_FOUND
from spider.output.diagnostics import SpiderError


class RuleQuery(Protocol):
    """A Rule as the store runs it: its id and the query that gives its Affected URLs."""

    @property
    def id(self) -> str: ...

    @property
    def reproduce_sql(self) -> str: ...


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
